// Service worker da urna: deixa a página abrir mesmo recarregada sem rede.
//
// Estratégia de atualização: rede primeiro.
// - Com rede, cada arquivo vem do servidor (revalidado, nunca do cache HTTP) e
//   atualiza a cópia guardada: a urna online roda sempre a versão publicada,
//   sem precisar de ação do mesário, e HTML e JS nunca ficam de versões diferentes.
// - Sem rede (ou servidor sem responder em 3s), usa a última cópia guardada.
// - Só os arquivos da própria urna passam por aqui; /api/ vai sempre direto à
//   rede. A fila de votos continua no localStorage, sem mudança.
// Trocar a estrutura do cache (lista de arquivos, nome) pede subir a VERSAO.
const VERSAO = "urna-v1";
const ARQUIVOS = ["/urna/", "/urna/urna.css", "/urna/urna.js", "/urna/manifest.json",
  "/urna/icone-192.png", "/urna/icone-512.png"];
const LIMITE_REDE = 3000;

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSAO).then((c) => c.addAll(ARQUIVOS.map((a) => new Request(a, { cache: "no-cache" })))));
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil((async () => {
    for (const nome of await caches.keys()) if (nome !== VERSAO) await caches.delete(nome);
    await self.clients.claim();
  })());
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin || !url.pathname.startsWith("/urna/")) return;
  e.respondWith(redePrimeiro(url));
});

async function redePrimeiro(url) {
  // o # (id e token da urna) não chega aqui; a ?query também não importa para arquivos estáticos
  const chave = url.pathname === "/urna/index.html" ? "/urna/" : url.pathname;
  const cache = await caches.open(VERSAO);
  try {
    const resposta = await Promise.race([
      fetch(chave, { cache: "no-cache" }),
      new Promise((_, falha) => setTimeout(() => falha(new Error("rede lenta")), LIMITE_REDE)),
    ]);
    if (resposta.ok) await cache.put(chave, resposta.clone());
    return resposta;
  } catch {
    return (await cache.match(chave)) ?? Response.error();
  }
}
