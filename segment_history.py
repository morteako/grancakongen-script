import argparse
import csv
import json
import os
import re
import shlex
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Callable, Dict, List, Optional, Tuple, Set
from urllib import request

SEGMENT_ID = os.getenv("STRAVA_SEGMENT_ID", "4580190")
SEGMENT_HISTORY_URL_TEMPLATE = "https://www.strava.com/athlete/segments/{segment_id}/history"
GOOGLE_SHEET_ID = "16-gb4q-aAdpWsrwcn-91vOEqSNfND9xp8Sku4QVDi9s"
GOOGLE_SHEET_GID = "2089954890"
GOOGLE_SHEET_EXPORT_URL = (
    f"https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID}/export"
    f"?format=tsv&gid={GOOGLE_SHEET_GID}"
)
UTOEVERE_SHEET_GID = os.getenv("GRANCAKONGEN_UTOEVERE_GID", "244792171")
UTOEVERE_SHEET_EXPORT_URL = (
    f"https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID}/export"
    f"?format=tsv&gid={UTOEVERE_SHEET_GID}"
)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
)

NAVN_CACHE_PATH = os.getenv(
    "GRANCAKONGEN_NAVN_PATH",
    os.path.join(os.getcwd(), ".grancakongen_navn"),
)

CURL_SNIPPET_PATH = os.getenv(
    "STRAVA_CURL_FILE",
    os.path.join(os.getcwd(), ".strava_curl"),
)

RESULTS_CSV_PATH = os.getenv(
    "GRANCAKONGEN_RESULTS_PATH",
    os.path.join(os.getcwd(), "results.csv"),
)


def _segment_history_url(segment_id: str) -> str:
    return SEGMENT_HISTORY_URL_TEMPLATE.format(segment_id=segment_id)


def parse_curl_headers(curl_command: str) -> Dict[str, str]:
    """Return headers from a copied cURL command."""

    if not curl_command:
        return {}

    normalized = (
        curl_command.replace("\\\r\n", " ")
        .replace("\\\n", " ")
        .replace("\r\n", "\n")
    )
    normalized = re.sub(r"(?:\^|`)\s*\n", " ", normalized)
    try:
        tokens = shlex.split(normalized, posix=True)
    except ValueError:
        return {}

    headers: Dict[str, str] = {}

    def _store(raw_value: str) -> None:
        if not raw_value or ":" not in raw_value:
            return
        name, value = raw_value.split(":", 1)
        header_name = name.strip().lower()
        if not header_name:
            return
        headers[header_name] = value.strip()

    idx = 0
    while idx < len(tokens):
        token = tokens[idx]
        header_value = ""
        cookie_value = ""
        lowered = token.lower()
        if token == "-H":
            idx += 1
            if idx < len(tokens):
                header_value = tokens[idx]
        elif lowered == "--header":
            idx += 1
            if idx < len(tokens):
                header_value = tokens[idx]
        elif lowered.startswith("--header="):
            header_value = token.split("=", 1)[1]
        elif token.startswith("-H") and len(token) > 2:
            header_value = token[2:]
        elif token == "-b":
            idx += 1
            if idx < len(tokens):
                cookie_value = tokens[idx]
        elif lowered == "--cookie":
            idx += 1
            if idx < len(tokens):
                cookie_value = tokens[idx]
        elif lowered.startswith("--cookie="):
            cookie_value = token.split("=", 1)[1]
        elif token.startswith("-b") and len(token) > 2:
            cookie_value = token[2:]
        if header_value:
            _store(header_value.strip())
        if cookie_value:
            cookie_text = cookie_value.strip()
            if cookie_text and not cookie_text.startswith("@"):
                headers["cookie"] = cookie_text
        idx += 1

    return headers


def _load_curl_headers(path: Optional[str] = None) -> Dict[str, str]:
    effective_path = path or CURL_SNIPPET_PATH
    if not effective_path:
        return {}
    try:
        with open(effective_path, "r", encoding="utf-8") as curl_file:
            return parse_curl_headers(curl_file.read())
    except (FileNotFoundError, OSError, UnicodeDecodeError):
        return {}


def _build_headers(
    cookie_header: Optional[str] = None,
    csrf_token: Optional[str] = None,
    segment_id: str = SEGMENT_ID,
) -> Dict[str, str]:
    curl_headers = _load_curl_headers()

    def _header_value(
        explicit: Optional[str], env_var: str, header_key: str
    ) -> str:
        if explicit and explicit.strip():
            return explicit.strip()
        env_value = (os.getenv(env_var) or "").strip()
        if env_value:
            return env_value
        header_value = (curl_headers.get(header_key) or "").strip()
        return header_value

    header_cookies = _header_value(cookie_header, "STRAVA_COOKIE_HEADER", "cookie")
    header_csrf = _header_value(csrf_token, "STRAVA_CSRF_TOKEN", "x-csrf-token")

    user_agent = (
        (os.getenv("STRAVA_USER_AGENT") or "").strip()
        or curl_headers.get("user-agent")
        or DEFAULT_USER_AGENT
    )

    if not header_cookies:
        raise ValueError("A Cookie header is required")
    if not header_csrf:
        raise ValueError("A CSRF token is required")

    return {
        "Accept": "application/javascript",
        "Cookie": header_cookies,
        "Referer": f"https://www.strava.com/segments/{segment_id}",
        "User-Agent": user_agent,
        "X-CSRF-Token": header_csrf,
        "X-Requested-With": "XMLHttpRequest",
    }


def fetch_segment_history(
    opener: Optional[Callable[[request.Request], Any]] = None,
    cookie_header: Optional[str] = None,
    csrf_token: Optional[str] = None,
    segment_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Return the JSON payload for the requested segment history."""

    segment_id_value = str(segment_id or SEGMENT_ID)
    headers = _build_headers(
        cookie_header=cookie_header, csrf_token=csrf_token, segment_id=segment_id_value
    )
    history_url = _segment_history_url(segment_id_value)
    http_request = request.Request(
        history_url,
        headers=headers,
        method="GET",
    )

    open_callable = opener or request.urlopen
    with open_callable(http_request) as response:
        payload = json.loads(response.read().decode("utf-8"))

    return payload


def _format_elapsed_time(seconds: Optional[float]) -> str:
    if seconds is None:
        return ""
    total_seconds = int(round(seconds))
    minutes, remaining = divmod(total_seconds, 60)
    return f"{minutes:02d}:{remaining:02d}"


def efforts_to_sheet_rows(
    efforts: List[Dict[str, Any]],
    segment_name_map: Optional[Dict[str, str]] = None,
    navn_value: Optional[str] = None,
) -> List[str]:
    rows = []
    navn_column = (navn_value or "NAVN").strip() or "NAVN"

    def _elapsed_seconds(value: Any) -> float:
        if value is None:
            return float("inf")
        try:
            return float(value)
        except (TypeError, ValueError):
            return float("inf")

    def _round_metric(value: Any) -> str:
        if value is None or value == "":
            return ""
        try:
            decimal_value = Decimal(str(value))
        except (InvalidOperation, ValueError):
            return ""
        try:
            rounded = decimal_value.to_integral_value(rounding=ROUND_HALF_UP)
        except InvalidOperation:
            return ""
        return str(int(rounded))

    best_by_year: Dict[Tuple[str, str], Dict[str, Any]] = {}
    order: List[Tuple[str, str]] = []
    for effort in efforts:
        date_str = effort.get("start_date_local") or effort.get("start_date") or ""
        year = date_str[:4] if len(date_str) >= 4 else ""
        segment_id = (
            (effort.get("segment") or {}).get("id")
            or effort.get("segment_id")
            or SEGMENT_ID
        )
        segment_id_str = str(segment_id)
        key = (segment_id_str, year)
        existing = best_by_year.get(key)
        if existing is None:
            best_by_year[key] = effort
            order.append(key)
        else:
            if _elapsed_seconds(effort.get("elapsed_time")) < _elapsed_seconds(
                existing.get("elapsed_time")
            ):
                best_by_year[key] = effort

    for segment_id_str, year in order:
        effort = best_by_year[(segment_id_str, year)]
        segment_display = (
            (segment_name_map or {}).get(segment_id_str, segment_id_str)
        )
        elapsed = _format_elapsed_time(effort.get("elapsed_time"))
        segment_effort_id = effort.get("id")
        effort_url = (
            f"https://www.strava.com/segment_efforts/{segment_effort_id}"
            if segment_effort_id
            else ""
        )
        avg_watts = _round_metric(
            effort.get("average_watts")
            or effort.get("avg_watts")
            or effort.get("watts")
            or ""
        )
        avg_bpm = _round_metric(
            effort.get("average_heartrate")
            or effort.get("average_hr")
            or effort.get("avg_hr")
            or ""
        )
        avg_cadence = _round_metric(
            effort.get("average_cadence") or effort.get("avg_cadence") or ""
        )

        row = "\t".join(
            [
                str(year),
                segment_display,
                navn_column,
                str(elapsed),
                effort_url,
                str(avg_watts),
                str(avg_bpm),
                str(avg_cadence),
            ]
        )
        rows.append(row)
    return rows


def fetch_segment_metadata(
    opener: Optional[Callable[[request.Request], Any]] = None,
) -> List[Dict[str, str]]:
    """Fetch Google Sheet metadata rows as a list of dicts."""

    req = request.Request(
        GOOGLE_SHEET_EXPORT_URL,
        headers={"Accept": "text/tab-separated-values"},
        method="GET",
    )
    open_callable = opener or request.urlopen
    with open_callable(req) as response:
        content = response.read().decode("utf-8-sig")

    reader = csv.DictReader(content.splitlines(), delimiter="\t")
    rows: List[Dict[str, str]] = [dict(row) for row in reader if any(row.values())]
    return rows


def _segment_id_from_link(link: str) -> str:
    if not link:
        return ""
    cleaned = link.strip()
    if not cleaned:
        return ""
    cleaned = cleaned.rstrip("/")
    last_part = cleaned.split("/")[-1]
    if "?" in last_part:
        last_part = last_part.split("?", 1)[0]
    if "#" in last_part:
        last_part = last_part.split("#", 1)[0]
    return last_part if last_part.isdigit() else ""


def build_segment_name_map(rows: List[Dict[str, str]]) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for row in rows:
        link = (row.get("Segment") or "").strip()
        id_navn = (row.get("Id-navn") or "").strip()
        segment_id = _segment_id_from_link(link)
        if segment_id and id_navn:
            mapping[segment_id] = id_navn
    return mapping


def extract_segment_ids(rows: List[Dict[str, str]]) -> List[str]:
    """Return unique segment ids from the metadata rows in sheet order."""

    segment_ids: List[str] = []
    seen: Set[str] = set()
    for row in rows:
        segment_id = _segment_id_from_link((row.get("Segment") or "").strip())
        if segment_id and segment_id not in seen:
            seen.add(segment_id)
            segment_ids.append(segment_id)
    return segment_ids


def fetch_athlete_names(
    limit: int = 6,
    opener: Optional[Callable[[request.Request], Any]] = None,
) -> List[str]:
    if limit <= 0:
        return []

    req = request.Request(
        UTOEVERE_SHEET_EXPORT_URL,
        headers={"Accept": "text/tab-separated-values"},
        method="GET",
    )

    open_callable = opener or request.urlopen
    try:
        with open_callable(req) as response:
            content = response.read().decode("utf-8-sig")
    except Exception:
        return []

    rows = list(csv.reader(content.splitlines(), delimiter="\t"))
    if not rows:
        return []

    header = rows[0]
    data_rows = rows[1:] if len(rows) > 1 else []
    column_index = 1 if len(header) > 1 else 0

    names: List[str] = []

    def _append_from_column(rows_iter: List[List[str]], index: int) -> None:
        for row in rows_iter:
            if index >= len(row):
                continue
            value = row[index].strip()
            if value:
                names.append(value)
            if len(names) >= limit:
                break

    _append_from_column(data_rows, column_index)

    if not names:
        reader = csv.DictReader(content.splitlines(), delimiter="\t")
        name_column: Optional[str] = None
        for row in reader:
            if name_column is None:
                for column in row.keys():
                    if column and "navn" in column.lower():
                        name_column = column
                        break
            cell_value = ""
            if name_column:
                cell_value = (row.get(name_column) or "").strip()
            else:
                for value in row.values():
                    if value and value.strip():
                        cell_value = value.strip()
                        break
            if cell_value:
                names.append(cell_value)
            if len(names) >= limit:
                break

    return names[:limit]


def _read_cached_navn(cache_path: str = NAVN_CACHE_PATH) -> str:
    if not cache_path:
        return ""
    try:
        with open(cache_path, "r", encoding="utf-8") as cache_file:
            return cache_file.read().strip()
    except FileNotFoundError:
        return ""
    except OSError:
        return ""


def _write_cached_navn(value: str, cache_path: str = NAVN_CACHE_PATH) -> None:
    if not cache_path:
        return
    directory = os.path.dirname(cache_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as cache_file:
        cache_file.write(value)


def load_or_prompt_navn(
    cache_path: str = NAVN_CACHE_PATH,
    input_func: Callable[[str], str] = input,
    suggested_names: Optional[List[str]] = None,
) -> str:
    cached = _read_cached_navn(cache_path=cache_path)
    if cached:
        return cached

    options = suggested_names
    if options is None:
        options = fetch_athlete_names()

    if options:
        print("Velg NAVN fra Utøvere-listen (skriv tallet eller et eget navn):")
        for idx, option in enumerate(options, start=1):
            print(f"{idx}. {option}")
        print("Skriv f.eks. 3. for å velge navn nummer 3, eller skriv inn et annet navn.")
    else:
        print("Fant ingen forslag fra Utøvere-fanen. Skriv inn navnet manuelt.")

    navn_input = input_func("NAVN: ").strip()
    if not navn_input:
        raise ValueError("NAVN kan ikke være tomt")

    navn_value = navn_input
    if options:
        selection = navn_input.rstrip(".")
        if selection.isdigit():
            index = int(selection) - 1
            if 0 <= index < len(options):
                navn_value = options[index]
            else:
                raise ValueError(
                    f"Ugyldig valg: skriv et tall mellom 1 og {len(options)} eller et navn."
                )

    if not navn_value:
        raise ValueError("NAVN kan ikke være tomt")

    _write_cached_navn(navn_value, cache_path=cache_path)
    return navn_value


def _write_results_csv(
    header_columns: List[str],
    rows: List[List[str]],
    path: str = RESULTS_CSV_PATH,
) -> None:
    if not path:
        return
    try:
        with open(path, "w", encoding="utf-8", newline="") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(header_columns)
            writer.writerows(rows)
    except OSError as exc:  # pragma: no cover - filesystem issues are user facing
        print(f"Failed to write {path}: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch Strava segment history and print as JSON or sheet rows."
    )
    parser.add_argument(
        "--all",
        dest="all_segments",
        action="store_true",
        help="Output tab-separated rows for all segments in Løpsinfo.",
    )
    parser.add_argument(
        "--json",
        dest="all_segments",
        action="store_false",
        help="Output the raw JSON payload(s) from Strava.",
    )
    parser.set_defaults(all_segments=True)
    args = parser.parse_args()

    segment_rows: List[Dict[str, str]] = []
    segment_name_map: Dict[str, str] = {}
    try:
        segment_rows = fetch_segment_metadata()
        segment_name_map = build_segment_name_map(segment_rows)
        print("Segment definitions (Id-navn -> Segment):")
        for row in segment_rows:
            id_navn = row.get("Id-navn", "")
            segment_link = row.get("Segment", "")
            if id_navn or segment_link:
                print(f"{id_navn}\t{segment_link}")
        print()
    except Exception as exc:  # pragma: no cover - optional network call
        print(f"Failed to fetch segment metadata: {exc}")

    segment_ids = extract_segment_ids(segment_rows)
    if not segment_ids:
        segment_ids = [str(SEGMENT_ID)]

    segment_histories: Dict[str, Dict[str, Any]] = {}
    for segment_id in segment_ids:
        try:
            segment_histories[segment_id] = fetch_segment_history(segment_id=segment_id)
        except Exception as exc:  # pragma: no cover - optional network call
            print(f"Failed to fetch history for segment {segment_id}: {exc}")

    if args.all_segments:
        navn_value = load_or_prompt_navn(
            suggested_names=fetch_athlete_names()
        )
        efforts: List[Dict[str, Any]] = []
        for segment_id in segment_ids:
            history = segment_histories.get(segment_id)
            if not history:
                continue
            efforts.extend(history.get("efforts", []))
        header_columns = [
            "År",
            "segment",
            "NAVN",
            "elapsed time (mm:ss)",
            "segment effort URL",
            "avg Watt",
            "avg Bpm",
            "avg Cadence",
        ]
        header = "\t".join(header_columns)
        sheet_rows = efforts_to_sheet_rows(
            efforts,
            segment_name_map=segment_name_map,
            navn_value=navn_value,
        )
        print(header)
        for row in sheet_rows:
            print(row)
        csv_rows: List[List[str]] = [row.split("\t") for row in sheet_rows]
        _write_results_csv(header_columns, csv_rows)
        print(f"\nSaved {len(csv_rows)} rows to {RESULTS_CSV_PATH}")
    else:
        if not segment_histories:
            print(json.dumps({}, indent=2))
        elif len(segment_histories) == 1:
            print(json.dumps(next(iter(segment_histories.values())), indent=2))
        else:
            print(json.dumps(segment_histories, indent=2))


if __name__ == "__main__":
    main()
