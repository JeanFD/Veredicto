// Efeitos sonoros, sintetizados na hora pelo Web Audio: nada de arquivo de áudio
// para baixar, e a urna offline toca igual (o service worker guarda este arquivo).
//
// O navegador só deixa tocar depois de um clique ou tecla na página. Um contexto
// criado fora disso nasce suspenso — sem erro nenhum, só sem som —, então
// Sons.preparar() precisa rodar dentro do clique (na urna e no celular, o próprio
// "Confirmar"); depois disso os sons podem sair a qualquer momento, até depois de
// um await. Sem áudio no navegador, tudo vira silêncio: a tela já diz o que houve.
window.Sons = (() => {
  let contexto = null;
  let ligado = true;

  function obter() {
    if (!contexto) {
      const Classe = window.AudioContext || window.webkitAudioContext;
      if (!Classe) return null;
      try {
        contexto = new Classe();
      } catch {
        return null;
      }
    }
    return contexto;
  }

  function preparar() {
    const c = obter();
    return c ? c.resume().catch(() => {}) : Promise.resolve();
  }

  function pronto() {
    return ligado && contexto?.state === "running";
  }

  // uma nota: frequência, início (s a partir de agora), duração, volume e timbre
  function nota(freq, { em = 0, dura = 0.2, volume = 0.2, tipo = "sine" } = {}) {
    if (!pronto()) return;
    try {
      const inicio = contexto.currentTime + em;
      const oscilador = contexto.createOscillator();
      const ganho = contexto.createGain();
      oscilador.type = tipo;
      oscilador.frequency.value = freq;
      // ataque curto para não estalar, e queda exponencial
      ganho.gain.setValueAtTime(0.0001, inicio);
      ganho.gain.exponentialRampToValueAtTime(volume, inicio + 0.01);
      ganho.gain.exponentialRampToValueAtTime(0.0001, inicio + dura);
      oscilador.connect(ganho).connect(contexto.destination);
      oscilador.start(inicio);
      oscilador.stop(inicio + dura + 0.02);
    } catch {
      // navegador sem áudio: fica o aviso na tela
    }
  }

  const sons = {
    // voto registrado: duas notas subindo, curtas e discretas
    voto() {
      nota(1046.5, { dura: 0.12, volume: 0.18 });
      nota(1568, { em: 0.1, dura: 0.25, volume: 0.18 });
    },
    // cronômetro começou a correr
    cronometroInicio() {
      nota(660, { dura: 0.15, volume: 0.15 });
    },
    // cada um dos últimos segundos do cronômetro
    cronometroTique() {
      nota(1200, { dura: 0.05, volume: 0.12, tipo: "square" });
    },
    // tempo esgotado: dois apitos
    cronometroFim() {
      nota(880, { dura: 0.35, volume: 0.25 });
      nota(880, { em: 0.45, dura: 0.7, volume: 0.25 });
    },
    // 3·2·1 da revelação; o 1 é o mais agudo
    regressiva(n) {
      nota({ 3: 440, 2: 523.3, 1: 659.3 }[n] ?? 440, { dura: 0.18, volume: 0.2, tipo: "triangle" });
    },
    // a apuração corre: tiques curtos que sobem conforme avança (0 a 1)
    apuracao(avanco) {
      nota(300 + avanco * 600, { dura: 0.04, volume: 0.06, tipo: "triangle" });
    },
    // fim da apuração: arpejo com vencedora, acorde neutro no empate
    vencedora() {
      [523.3, 659.3, 784, 1046.5].forEach((f, i) =>
        nota(f, { em: i * 0.11, dura: i === 3 ? 0.9 : 0.3, volume: 0.18, tipo: "triangle" }));
    },
    empate() {
      [523.3, 622.3, 784].forEach((f) => nota(f, { dura: 0.8, volume: 0.12, tipo: "triangle" }));
    },
  };

  return {
    ...sons,
    preparar,
    pronto,
    obter,
    ligar(sim) { ligado = sim; },
    get ligado() { return ligado; },
  };
})();
