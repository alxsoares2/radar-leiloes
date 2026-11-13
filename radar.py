"""Local vehicle auction dashboard and read-only collector."""
import argparse
import json
import re
import threading
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "coleta.json"
MEGA = "https://www.megaleiloes.com.br"
PATIO = "https://patiovitoriadaconquista.com"
INDEXES = (
    ("Mega Leilões", f"{MEGA}/veiculos"),
    ("Pátio Vitória da Conquista", f"{PATIO}/"),
)
LIMIT = 8 * 1024 * 1024
PROCESS = r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}"
MONEY = r"R\$\s*([\d.]+,\d{2})"
lock = threading.Lock()


def download(url):
    with requests.get(url, timeout=(6, 12), stream=True, headers={"User-Agent": "RadarLeiloes/0.1"}) as response:
        response.raise_for_status()
        chunks = bytearray()
        for chunk in response.iter_content(65536):
            chunks.extend(chunk)
            if len(chunks) > LIMIT:
                raise ValueError("Arquivo excede o limite de leitura.")
        return bytes(chunks)


def html(url):
    return BeautifulSoup(download(url), "html.parser")


def clean(value):
    return " ".join(value.split())


def normalized(value):
    return "".join(c for c in unicodedata.normalize("NFD", value.lower()) if not unicodedata.combining(c))


def first(pattern, value):
    result = re.search(pattern, value, re.I)
    return result.group(1) if result else None


def amount(value):
    return float(value.replace(".", "").replace(",", ".")) if value else None


def lot_photos(soup, url):
    host = urlsplit(url).hostname
    photos = []
    for tag in soup.select('meta[property="og:image"], a[href], img'):
        for key in ('content', 'href', 'data-src', 'src'):
            raw = tag.get(key)
            if not raw:
                continue
            image = urljoin(url, raw)
            target = urlsplit(image)
            if target.scheme != 'https' or not re.search(r'\.(jpg|jpeg|png|webp)(?:[&?]|$)', image, re.I):
                continue
            same_mega_lot = (host == 'www.megaleiloes.com.br' and target.hostname == 'cdn1.megaleiloes.com.br'
                             and re.search(r'/batches/(\d+)/', target.path)
                             and target.path.split('/')[2] == urlsplit(url).path.lower().rstrip('/').rsplit('-j', 1)[-1])
            patio_gallery = (host == target.hostname == 'patiovitoriadaconquista.com'
                             and re.search(r'(?:id=lotes_\d+_|id=mais-fotos_)', target.query))
            if (same_mega_lot or patio_gallery) and image not in photos:
                photos.append(image)
    return photos[:8]


def category(name):
    name = normalized(name)
    groups = (
        ("Caminhonete", r"caminhonete|picape|\bhilux\b|\bfrontier\b|\branger\b|\btoro\b|\bsaveiro\b|\bstrada\b"),
        ("SUV", r"\bsuv\b|\bcreta\b|\btracker\b|\bkicks\b|t.cross|hr.v|\bcompass\b|\brenegade\b|\btaos\b|\bsportage\b|\bterritory\b|\btucson\b|\bduster\b|\bbronco\b|\bpulse\b|\bfastback\b|corolla cross"),
        ("Van", r"\bvan\b|ducato|sprinter|jumper|furg[aã]o|master"),
        ("Caminhão", r"caminhao|cavalo mecanico"),
        ("Ônibus", r"\bonibus\b|\bmicro.onibus\b"),
        ("Moto", r"\bmoto\b|motocicleta|scooter|quadriciclo"),
    )
    for label, pattern in groups:
        if re.search(pattern, name):
            return label
    return "Carro" if re.search(r"carro|automovel|corolla|vectra|civic", name) else "Outro"


def dates(value):
    result = []
    for match in re.finditer(r"(?:([123])ª Praça:\s*)?(\d{2}/\d{2}/\d{4})\s*(?:às\s*)?(\d{2}:\d{2})(?:\s*(?:Horário de Brasília)?\s*" + MONEY + r")?", value, re.I):
        stage, day, hour, price = match.groups()
        try:
            closing = datetime.strptime(f"{day} {hour} -0300", "%d/%m/%Y %H:%M %z")
        except ValueError:
            continue
        result.append((closing, stage, amount(price)))
    return result


def payment_fields(document):
    text = normalized(clean(document))
    clause = first(r"\b(?:do[s]? pagamento[s]?|forma de pagamento)\s*[:–-]\s*(.{15,570})", text) or ""
    item_clause = re.split(r"\b(?:da comissao|da proposta|a comissao|pagamento da comissao)\b", clause)[0]
    payment = "A confirmar"
    for label, pattern in (
        ("Guia judicial", r"guia de deposito judicial"),
        ("Boleto", r"\bboleto\b"),
        ("Pix", r"\bpix\b"),
        ("Transferência", r"\bted\b|transferencia bancaria"),
    ):
        if re.search(pattern, item_clause):
            payment = label
            break

    no_installment = re.search(r"(?:nao (?:sera[o]? |se )?(?:aceit\w+|admit\w+|permit\w+|havera)|nao admite)[^.]{0,65}(?:parcel|prestac)|(?:pagamento|lance[s]?)\s+(?:somente|exclusivamente|unicamente)\s+a vista", text)
    installment = "Somente à vista" if no_installment else "A confirmar"
    terms = None
    if not no_installment:
        terms = first(r"((?:interessad[oa]s? (?:em |na )?|proposta de pagamento)[^.]{0,210}(?:parcelad|presta[cç])[^.]{0,270})", document)
        if re.search(r"(?:apresentar|aceit\w+|oferecer|admite.se)[^.]{0,130}(?:proposta|pagamento)[^.]{0,100}(?:parcelad|prestac)|proposta de pagamento parcelado", text):
            installment = "Aceita proposta"
    balance = "Confirmado" if re.search(r"(?:saldo|parcelas)\s+(?:ser[aã]o? |dever[aã]o? )?(?:pag[oa]s?|quitad[oa]s?)\s+(?:por|via|mediante|atraves de)\s+boleto", text) else "A confirmar"
    return {
        "payment": payment,
        "installment": installment,
        "balanceBoleto": balance,
        "terms": clean(terms)[:280] if terms else None,
    }


def parse_lot(soup, url, source, notice_text=""):
    title = next((item for item in soup.find_all("h1") if not normalized(clean(item.get_text(" ", strip=True))).startswith("leilao de ")), None)
    name = clean(title.get_text(" ", strip=True)) if title else ""
    if not name or normalized(name) in {"leilao de veiculos", "leilao de utilitarios", "mega leiloes"}:
        return None
    body = clean(soup.get_text(" ", strip=True))
    folded = normalized(body)
    notices = []
    for link in soup.find_all("a", href=True):
        if "edital" in normalized(link.get_text(" ", strip=True)):
            target = urljoin(url, link["href"])
            host = urlsplit(target).hostname or ""
            if urlsplit(target).scheme == "https" and (host.endswith(".megaleiloes.com.br") or host == urlsplit(url).hostname):
                if ".pdf" in target.lower():
                    notices.append(target)
    process = first(r"(" + PROCESS + r")", notice_text or body)
    mode = "A confirmar"
    if process and re.search(r"\bjudicial\b", normalized(notice_text) if notice_text else folded.partition(normalized(name))[2][:1700]):
        mode = "Judicial"
    elif re.search(r"\bextrajudicial\b", folded.partition(normalized(name))[2][:450]):
        mode = "Extrajudicial"
    elif re.search(r"\b(?:detran|prefeitura|policia rodoviaria federal)\b", normalized(name)):
        mode = "Administrativo"
    year = first(r"\bAno Modelo\s*:?\s*(20\d{2}|19\d{2})", body)
    manufacture = first(r"\bAno de Fabricação\s*:?\s*(20\d{2}|19\d{2})", body)
    pair = re.search(r"\b(20\d{2}|19\d{2}|\d{2})\s*/\s*(20\d{2}|19\d{2}|\d{2})\s*$", name)
    if pair:
        start, end = map(int, pair.groups())
        manufacture = manufacture or (start if start >= 100 else start + (1900 if start >= 70 else 2000))
        year = year or (end if end >= 100 else end + (1900 if end >= 70 else 2000))
    year = year or first(r"\b((?:19|20)\d{2})\s*$", name)
    closing = dates(body)
    stages = [item for item in closing if item[1]]
    upcoming = [item for item in stages if item[0] >= datetime.now().astimezone()]
    selected = (min(upcoming) if upcoming else max(stages)) if stages else None
    if not selected:
        closing_match = first(r"Fechamento:\s*(\d{2}/\d{2}/\d{4}\s+às\s+\d{2}:\d{2})", body)
        selected = next(iter(dates(closing_match or "")), None)
    price = amount(first(r"(?:Próximo lance mínimo|Valor inicial|Lance Inicial)\s*" + MONEY, body))
    if selected and selected[2] is not None:
        price = selected[2]
    location = re.search(r"Localização\s+([A-Za-zÀ-ž .'-]{2,55}),\s*([A-Z]{2})\b", body)
    city, uf = location.groups() if location and location[2] != "SI" else (None, None)
    commission = first(r"(?:a título de comissão.{0,100}|comissão do leiloeiro\s*[:–-]?\s*)(\d{1,2}(?:,\d{1,2})?)\s*%", clean(notice_text))
    status = "Cancelado" if re.search(r"leil[aã]o cancelado|lote cancelado", body[:2500], re.I) else None
    id_match = re.search(r"-(j\d+)$", urlsplit(url).path, re.I)
    lot_id = f"mega:{id_match[1].upper()}" if id_match else f"patio:{urlsplit(url).path.strip('/').split('/')[-1]}"
    photos = lot_photos(soup, url)
    return {
        "id": lot_id, "name": name, "source": source, "url": url, "notice": next(iter(notices), None),
        "category": category(name), "mode": mode, "year": int(year) if year else None,
        "manufacture": int(manufacture) if manufacture else None, "process": process,
        "city": city, "uf": uf, "status": status, "price": price, "priceType": "Lance publicado",
        "end": selected[0].isoformat() if selected else None,
        "stage": f"{selected[1]}ª praça" if selected and selected[1] else None,
        "commission": float(commission.replace(",", ".")) if commission else None,
        "photos": photos or None,
        "illustrative": bool(re.search(r'\b(?:imagem|foto)s? meramente ilustrativa', folded)) if photos else None,
        **payment_fields(notice_text),
    }


def collect_source(name, index, max_lots):
    soup = html(index)
    links = {}
    for anchor in soup.find_all("a", href=True):
        url = urljoin(index, anchor["href"]).split("?")[0].split("#")[0]
        target = urlsplit(url)
        if target.hostname != urlsplit(index).hostname or target.scheme != "https":
            continue
        pattern = r"^/veiculos/.+-j\d+/?$" if name == "Mega Leilões" else r"^/lote/[^/]+/\d+/?$"
        if re.match(pattern, target.path, re.I):
            links[url.rstrip("/")] = None
    if not links:
        raise ValueError("Nenhum link de lote reconhecido no catálogo.")
    lots, errors = [], 0
    for url in list(links)[:max_lots]:
        try:
            page = html(url)
            lot = parse_lot(page, url, name)
            if not lot:
                errors += 1
                continue
            if lot["notice"]:
                try:
                    pdf = PdfReader(BytesIO(download(lot["notice"])))
                    notice = "\n".join(page.extract_text() or "" for page in pdf.pages[:18])
                    if not notice.strip():
                        raise ValueError("PDF sem camada de texto.")
                    lot = parse_lot(page, url, name, notice)
                except Exception as error:
                    lot["notes"] = f"Edital não interpretado ({type(error).__name__}). Consulte o PDF."
                    errors += 1
            lots.append(lot)
        except (OSError, ValueError, requests.RequestException):
            errors += 1
    return lots, errors


def read_data():
    from cloud import cloud_database
    database = cloud_database()
    if database:
        current = database.read()
        if current:
            return current
        return json.loads((ROOT / "seed.json").read_text(encoding="utf-8"))
    for path in (CACHE, ROOT / "seed.json"):
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    raise FileNotFoundError("Amostra inicial não encontrada.")


def refresh(max_lots):
    from cloud import cloud_database
    previous = read_data()
    lots = {item["id"]: item for item in previous["lots"]}
    sources = {item["name"]: item for item in previous["sources"]}
    successes = 0
    with ThreadPoolExecutor(max_workers=len(INDEXES)) as pool:
        tasks = [(name, index, pool.submit(collect_source, name, index, max_lots)) for name, index in INDEXES]
        for name, index, task in tasks:
            try:
                found, errors = task.result()
                for lot in found:
                    earlier = lots.get(lot["id"], {})
                    if lot["installment"] == "A confirmar" and earlier.get("installment") == "Aceita proposta" and lot.get("notice") == earlier.get("notice"):
                        for key in ("installment", "payment", "balanceBoleto", "terms"):
                            lot[key] = earlier.get(key)
                    lots[lot["id"]] = {**earlier, **{key: value for key, value in lot.items() if value is not None}}
                if found:
                    successes += 1
                status = "Consultado" if not errors else f"Falha parcial ({errors} ocorrência(s))"
                sources[name] = {**sources.get(name, {}), "name": name, "url": index, "status": status, "count": len(found)}
            except (OSError, ValueError, requests.RequestException) as error:
                sources[name] = {**sources.get(name, {}), "name": name, "url": index, "count": 0, "status": f"Falha ({type(error).__name__})"}
    result = {
        **previous,
        "at": datetime.now().astimezone().isoformat() if successes else previous["at"],
        "kind": "Coleta local e amostra inicial" if successes else previous["kind"],
        "lots": list(lots.values()), "sources": list(sources.values()),
    }
    database = cloud_database()
    if database:
        database.save(result)
    else:
        temp = CACHE.with_suffix(".tmp")
        temp.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(CACHE)
    return result


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / "dist"), **kwargs)

    def json_response(self, data):
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path == "/api/lots":
            self.json_response(read_data())
        elif self.path in {"/", "/index.html", "/app.js", "/style.css", "/data.js"}:
            super().do_GET()
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != "/api/refresh":
            self.send_error(404)
            return
        origin = self.headers.get("Origin")
        expected = f"http://{self.headers.get('Host')}"
        if origin and origin != expected:
            self.send_error(403)
            return
        if not lock.acquire(blocking=False):
            self.send_error(409)
            return
        try:
            self.json_response(refresh(self.server.max_lots))
        finally:
            lock.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--max-lots", type=int, choices=range(1, 51), metavar="1–50", default=8)
    parser.add_argument("--collect", action="store_true")
    args = parser.parse_args()
    if args.collect:
        data = refresh(args.max_lots)
        print(json.dumps({"lotes": len(data["lots"]), "fontes": data["sources"]}, ensure_ascii=False, indent=2))
        if not any(source.get("count", 0) > 0 for source in data["sources"] if source["name"] in dict(INDEXES)):
            raise SystemExit(1)
        return
    with ThreadingHTTPServer(("127.0.0.1", args.port), Handler) as server:
        server.max_lots = args.max_lots
        print(f"Radar disponível em http://127.0.0.1:{args.port}", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()


