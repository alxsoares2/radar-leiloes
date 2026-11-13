(() => {
  const el = id => document.getElementById(id);
  const filters = el("filters");
  const money = new Intl.NumberFormat("pt-BR", {style:"currency",currency:"BRL"});
  const date = new Intl.DateTimeFormat("pt-BR", {dateStyle:"short",timeStyle:"short",timeZone:"America/Fortaleza"});
  const normalize = value => String(value ?? "").normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();
  const format = value => Number.isFinite(value) ? money.format(value) : "A confirmar";
  const timestamp = lot => Date.parse(lot.end);
  const place = lot => [lot.city,lot.uf].filter(Boolean).join(", ") || "Retirada a confirmar";
  const state = (lot, now) => lot.status || (!Number.isFinite(timestamp(lot)) ? "Sem data" : timestamp(lot) > now ? "A encerrar" : "Encerrado");
  let data = window.RADAR_DATA;
  let visible = [];
  let fromServer = false;

  function node(tag, value, className) {
    const element = document.createElement(tag);
    if (value != null) element.textContent = value;
    if (className) element.className = className;
    return element;
  }
  function field(id) { return el(id).value; }
  function between(value, low, high) {
    return (!low && !high) || (Number.isFinite(value) && (!low || value >= Number(low)) && (!high || value <= Number(high)));
  }
  function setOptions(id, values) {
    const select = el(id);
    const previous = select.value;
    select.options.length = 1;
    for (const value of values) select.add(new Option(value));
    if (values.includes(previous)) select.value = previous;
  }
  function show(title, ...contents) {
    el("dialogTitle").textContent = title;
    el("dialogBody").replaceChildren(...contents);
    if (!el("dialog").open) el("dialog").showModal();
  }
  function anchor(label, url) {
    if (!url || !/^https?:\/\//i.test(url)) return null;
    const link = node("a",label);
    link.href = url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    return link;
  }
  function thumbnail(lot, className = "thumbnail") {
    const frame = node("div",null,className);
    const empty = node("span","Sem foto publicada");
    frame.append(empty);
    const url = lot.photos?.[0];
    if (!url || !/^https:\/\//i.test(url)) return frame;
    const img = node("img");
    img.alt = lot.illustrative ? "Imagem ilustrativa de " + lot.name : "Foto publicada para " + lot.name;
    img.loading = "lazy";
    img.referrerPolicy = "no-referrer";
    img.hidden = true;
    img.addEventListener("load",() => {
      empty.hidden = true;
      img.hidden = false;
      if (lot.illustrative) frame.append(node("small","Ilustrativa","photo-label"));
    },{once:true});
    img.addEventListener("error",() => { empty.textContent = "Foto indisponível"; },{once:true});
    frame.append(img);
    img.src = url;
    return frame;
  }
  function sourceOrigins(source) {
    const group = node("div",null,"source-origins");
    for (const entry of source.origins || []) {
      const board = (data.boards || []).find(item => item.uf === entry.uf);
      const registration = node("p",[board?.board || entry.uf, "Matrícula " + entry.registration, entry.auctioneer].join(" · "));
      const links = node("p",null,"detail-links");
      links.append(...[anchor("Consultar Junta",board?.registry),anchor(entry.evidenceLabel || "Ver documento",entry.evidence)].filter(Boolean));
      group.append(registration,links);
    }
    if (!group.children.length) group.append(node("p","Junta e matrícula a confirmar"));
    return group;
  }
  function details(lot) {
    const fields = [
      ["Tipo",lot.category],["Modalidade",lot.mode],["Ano fabricação / modelo",[lot.manufacture,lot.year].filter(Boolean).join(" / ")],
      ["Retirada",place(lot)],["Praça",lot.stage],["Encerramento",Number.isFinite(timestamp(lot)) ? date.format(timestamp(lot)) : null],
      [lot.priceType || "Lance",format(lot.price)],["Avaliação",format(lot.valuation)],
      ["Comissão",Number.isFinite(lot.commission) ? lot.commission + "%" : null],
      ["Taxas adicionais",format(lot.fees)],["Pagamento do arremate",lot.payment],["Parcelamento",lot.installment],
      ["Entrada / parcelas",lot.terms],["Boleto do saldo",lot.balanceBoleto],["Condição",lot.condition],
      ["Vara",lot.court],["Processo",lot.process],["Fonte",lot.source]
    ];
    const dl = node("dl");
    for (const [label,value] of fields) dl.append(node("dt",label),node("dd",value || "A confirmar"));
    const links = node("p",null,"detail-links");
    links.append(...[anchor("Abrir lote",lot.url),anchor("Abrir edital",lot.notice)].filter(Boolean));
    const evidence = lot.notes ? node("p",lot.notes) : node("p","Consulte as condições no portal do leiloeiro.");
    const gallery = node("div",null,"gallery");
    for (const photo of lot.photos || []) gallery.append(thumbnail({...lot,photos:[photo]},"thumbnail"));
    show(lot.name,...(gallery.children.length ? [gallery] : []),dl,evidence,links);
  }
  function card(lot) {
    const item = node("article",null,"item");
    const info = node("div");
    info.append(node("span",lot.mode,"badge"),node("span",lot.category,"badge alt"),node("h3",lot.name),node("p",[lot.year,place(lot)].filter(Boolean).join(" · ")),node("p",lot.source));
    const price = node("div");
    price.append(node("p",lot.priceType || "Lance"),node("strong",format(lot.price)),node("p",lot.installment));
    const when = node("div",null,"when");
    when.append(node("p",lot.stage || "Praça"),node("strong",Number.isFinite(timestamp(lot)) ? date.format(timestamp(lot)) : "Sem data"),node("p",state(lot,Date.now())));
    const button = node("button","Ver lote");
    button.type = "button";
    button.addEventListener("click",() => details(lot));
    item.append(thumbnail(lot),info,price,when,button);
    return item;
  }
  function render() {
    const now = Date.now();
    const words = normalize(field("query")).trim().split(/\s+/).filter(Boolean);
    visible = data.lots.filter(lot => {
      const text = normalize([lot.name,lot.city,lot.uf,lot.process,lot.source].filter(Boolean).join(" "));
      return words.every(word => text.includes(word))
        && ["category","mode","uf","condition","installment","payment"].every(key => !field(key) || field(key) === lot[key])
        && (!field("status") || field("status") === state(lot,now))
        && between(lot.year,field("minYear"),field("maxYear"))
        && between(lot.price,field("minPrice"),field("maxPrice"))
        && (!el("boleto").checked || lot.balanceBoleto === "Confirmado")
        && (!el("official").checked || lot.notice);
    });
    const end = lot => Number.isFinite(timestamp(lot)) ? timestamp(lot) : Infinity;
    const proximity = lot => end(lot) < now ? 1 : 0;
    const ordering = {
      recent:(a,b) => proximity(a)-proximity(b) || (proximity(a) ? end(b)-end(a) : end(a)-end(b)),
      price:(a,b) => (a.price ?? Infinity)-(b.price ?? Infinity),
      year:(a,b) => (b.year ?? 0)-(a.year ?? 0)
    };
    visible.sort(ordering[field("sort")]);
    el("count").textContent = visible.length + (visible.length === 1 ? " lote" : " lotes") + " de " + data.lots.length;
    el("export").disabled = !visible.length;
    el("cards").replaceChildren(...(visible.length ? visible.map(card) : [node("p","Nenhum lote corresponde aos filtros selecionados.","empty")]));
  }
  function useData(next) {
    data = next;
    setOptions("uf",[...new Set(data.lots.map(lot => lot.uf).filter(Boolean))].sort());
    setOptions("condition",[...new Set(data.lots.map(lot => lot.condition).filter(Boolean))].sort());
    el("dataset").textContent = data.kind + (data.at ? " · " + data.at.slice(0,10).split("-").reverse().join("/") : "");
    render();
  }
  function csvCell(value) {
    let content = String(value ?? "");
    if (typeof value === "string" && /^[\s]*[=+@-]/.test(content)) content = "'" + content;
    return '"' + content.replaceAll('"','""') + '"';
  }
  el("export").addEventListener("click",() => {
    const columns = {name:"Veículo",category:"Tipo",year:"Ano-modelo",mode:"Modalidade",uf:"UF",city:"Retirada",price:"Lance",priceType:"Referência do lance",end:"Encerramento",commission:"Comissão (%)",installment:"Parcelamento",payment:"Pagamento",balanceBoleto:"Boleto do saldo",process:"Processo",source:"Fonte",url:"Lote",notice:"Edital"};
    const lines = [Object.values(columns),...visible.map(lot => Object.keys(columns).map(key => lot[key]))];
    const url = URL.createObjectURL(new Blob(["\uFEFF"+lines.map(line => line.map(csvCell).join(";")).join("\r\n")],{type:"text/csv;charset=utf-8"}));
    const link = node("a");
    link.href = url;
    link.download = "lotes-filtrados.csv";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url),1000);
  });
  el("sources").addEventListener("click",() => {
    const list = node("div",null,"source-list");
    const registryLink = node("p",null,"detail-links");
    const filter = node("select");
    filter.setAttribute("aria-label","Junta de origem");
    filter.add(new Option("Todas as Juntas",""));
    filter.add(new Option("Origem a confirmar","pending"));
    for (const board of data.boards || []) {
      filter.add(new Option([board.uf,board.board || board.name].join(" · "),board.uf));
    }
    const draw = () => {
      list.replaceChildren();
      registryLink.replaceChildren();
      const board = (data.boards || []).find(item => item.uf === filter.value);
      const official = anchor(board?.registry ? "Consultar cadastro de leiloeiros" : "Abrir portal da Junta",board?.registry || board?.website);
      if (official) registryLink.append(official);
      for (const source of data.sources) {
        const origins = source.origins || [];
        if (filter.value === "pending" && origins.length) continue;
        const matching = filter.value && filter.value !== "pending" ? origins.filter(item => item.uf === filter.value) : origins;
        if (filter.value && filter.value !== "pending" && !matching.length) continue;
        const item = node("section");
        const title = node("h3");
        title.append(anchor(source.name,source.url) || source.name);
        item.append(title,node("p",source.status+(source.count != null ? " · "+source.count+" lote(s)" : "")),sourceOrigins({...source,origins:matching}));
        list.append(item);
      }
      if (!list.children.length) list.append(node("p","Nenhuma fonte vinculada a esta Junta na base atual."));
    };
    filter.addEventListener("change",draw);
    draw();
    show("Fontes",filter,registryLink,list);
  });
  el("clear").addEventListener("click",() => {
    filters.reset();
    el("query").value = "";
    el("sort").value = "recent";
    render();
  });
  filters.addEventListener("submit",event => event.preventDefault());
  filters.addEventListener("input",render);
  el("query").addEventListener("input",render);
  el("sort").addEventListener("change",render);
  el("close").addEventListener("click",() => el("dialog").close());
  el("reload").addEventListener("click",async () => {
    if (!fromServer) return;
    const button = el("reload");
    const message = el("error");
    button.disabled = true;
    button.textContent = "Consultando fontes…";
    message.hidden = true;
    try {
      const response = await fetch("api/refresh",{method:"POST"});
      if (!response.ok) throw new Error();
      const next = await response.json();
      useData(next);
      if (next.sources.some(source => source.status.startsWith("Falha"))) {
        message.textContent = "Algumas fontes falharam. Consulte Fontes para ver quais.";
        message.hidden = false;
      }
    } catch {
      message.textContent = "Não foi possível atualizar. Os lotes anteriores continuam disponíveis.";
      message.hidden = false;
    } finally {
      button.disabled = false;
      button.textContent = "Atualizar coleta";
    }
  });
  useData(data);
  if (/^https?:$/.test(location.protocol)) {
    fetch("api/lots").then(response => response.ok ? response.json() : null).then(next => {
      if (!next || !Array.isArray(next.lots)) return;
      fromServer = true;
      el("reload").hidden = next.manualRefresh === false;
      useData(next);
    }).catch(() => {});
  }
})();

