// A stand-in for AivisSpeech's /audio_query and /synthesis, for tests and
// for trying the pipeline on a machine without the engine. Each kana is a
// mora of its own vowel; anything else counts as a short "a". The voice is
// a soft tone as long as the query says.

import { queryDuration, type AudioQuery, type Mora } from "../src/visemes";

const VOWEL_ROWS: Record<string, string> = {
  a: "あかさたなはまやらわがざだばぱぁゃアカサタナハマヤラワガザダバパァャ",
  i: "いきしちにひみりぎじぢびぴぃイキシチニヒミリギジヂビピィ",
  u: "うくすつぬふむゆるぐずづぶぷぅゅウクスツヌフムユルグズヅブプゥュ",
  e: "えけせてねへめれげぜでべぺぇエケセテネヘメレゲゼデベペェ",
  o: "おこそとのほもよろをごぞどぼぽぉょオコソトノホモヨロヲゴゾドボポォョ",
};

function mora(ch: string): Mora | null {
  if ("、。！？「」 ".includes(ch)) return null;
  if ("んン".includes(ch)) return { text: ch, vowel: "N", vowel_length: 0.08 };
  if ("っッ".includes(ch)) return { text: ch, vowel: "cl", vowel_length: 0.07 };
  const vowel = Object.entries(VOWEL_ROWS).find(([, row]) => row.includes(ch))?.[0] ?? "a";
  const consonant = "あいうえおアイウエオ".includes(ch)
    ? null
    : "まみむめもマミムメモ".includes(ch)
      ? "m"
      : "ばびぶべぼぱぴぷぺぽバビブベボパピプペポ".includes(ch)
        ? "b"
        : "k";
  return { text: ch, consonant, consonant_length: consonant ? 0.05 : null, vowel, vowel_length: 0.09 };
}

export function mockQuery(text: string): AudioQuery {
  const phrases = text.split(/[、。！？]/).filter((p) => p.trim());
  return {
    speedScale: 1,
    prePhonemeLength: 0.1,
    postPhonemeLength: 0.1,
    accent_phrases: phrases.map((p) => ({
      moras: [...p].map(mora).filter((m): m is Mora => m !== null),
      pause_mora: { text: "、", vowel: "pau", vowel_length: 0.25 },
    })),
  };
}

export function toneWav(seconds: number, rate = 24000): Uint8Array {
  const n = Math.round(seconds * rate);
  const bytes = new Uint8Array(44 + n * 2);
  const view = new DataView(bytes.buffer);
  const text = (offset: number, s: string) => [...s].forEach((c, i) => view.setUint8(offset + i, c.charCodeAt(0)));
  text(0, "RIFF");
  view.setUint32(4, 36 + n * 2, true);
  text(8, "WAVEfmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, rate, true);
  view.setUint32(28, rate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  text(36, "data");
  view.setUint32(40, n * 2, true);
  for (let i = 0; i < n; i++) view.setInt16(44 + i * 2, Math.sin((i / rate) * 2 * Math.PI * 220) * 6000, true);
  return bytes;
}

export function serveMock(port = 0) {
  return Bun.serve({
    port,
    async fetch(request) {
      const url = new URL(request.url);
      if (url.pathname === "/audio_query") return Response.json(mockQuery(url.searchParams.get("text") ?? ""));
      if (url.pathname === "/synthesis") {
        const query = (await request.json()) as AudioQuery;
        return new Response(toneWav(queryDuration(query)).buffer as ArrayBuffer, { headers: { "content-type": "audio/wav" } });
      }
      if (url.pathname === "/speakers") return Response.json([{ name: "mock", styles: [{ id: 1, name: "normal" }] }]);
      return new Response("not found", { status: 404 });
    },
  });
}

if (import.meta.main) {
  const server = serveMock(Number(process.argv[2] ?? 10101));
  console.log(`mock speech engine on http://127.0.0.1:${server.port}`);
}
