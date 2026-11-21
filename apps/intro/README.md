# OpenCut intro — virtual idol intros

Remotion scenes in which a 2D avatar says the lesson's opening line, its
mouth following the vowels AivisSpeech (or VOICEVOX) reports for each mora:
あいうえお, closed for ん, っ, pauses and ま・ば・ぱ. She breathes, sways
and blinks, and the lesson's title is on a card
beside her.

## Make an intro

1. Write a scene, e.g. `scenes/n4-teshimau.json`:

   ```json
   {
     "scene_type": "intro",
     "avatar": "izumi",
     "subtitle": "N4 文法",
     "title": "～てしまう",
     "text": "みなさん、こんにちは。N4文法の授業へようこそ。今日は「てしまう」を勉強しましょう。",
     "translation": "Xin chào các bạn. Chào mừng đến với bài học ngữ pháp N4. …",
     "speaker": 1431611904
   }
   ```

   `speaker` is an AivisSpeech style id (the same ids as textts' `roles.yaml`);
   left out, the engine's first voice speaks. `speed` (1 = normal) and
   `colors` (`["#eff6ff", "#1e3a8a"]`, the background) are optional.

2. With AivisSpeech running, voice it, then render it:

   ```sh
   bun install
   bun run speak scenes/n4-teshimau.json      # public/voices/…wav + scenes/…props.json
   bun run render scenes/n4-teshimau.props.json   # out/n4-teshimau.mp4 (H.264 + AAC)
   ```

   VOICEVOX instead: `bun run speak scenes/x.json --engine http://127.0.0.1:50021`.
   `bun run studio` opens Remotion Studio to preview and tweak.

3. Put it in front of the lesson:

   ```sh
   opencut import-textts tt/bai10.mp3 --script bai10.txt --intro apps/intro/out/n4-teshimau.mp4 -o lesson/bai10.project.json
   opencut render lesson/bai10.project.json
   ```

   The lesson's audio, slides, subtitles and markers move after the intro;
   `--outro` adds a closing clip the same way. `scenes/outro.json` is a
   ready outro (Izumi points the lesson's learners to QBank): voice and
   render it exactly like an intro.

No engine at hand? `bun run scripts/mock-engine.ts` serves a stand-in on
port 10101 (a tone instead of a voice, rough mora timing) to try the pipeline.

## Lesson visuals (charts, diagrams, effects for the body)

The body of a lesson gets pictures that change with each sentence: a soft pastel
background and one **scene** per stretch of subtitle cues. Remotion renders them
as one silent 1920x1080 video; OpenCut lays the voice, subtitles and the chibi on it.

```sh
# 1. Claude (or you) writes <lesson>.visuals.json from the script, cue by cue.
# 2. Look at one still per scene, fix the JSON, repeat:
node scripts/lesson.ts preview scenes/ptc-vi.visuals.json ../../lessons/ptc-vi/ptc-vi.project.json
# 3. Render the background and make it the project's picture:
node scripts/lesson.ts build scenes/ptc-vi.visuals.json my.project.json
opencut mascot my.project.json --avatar apps/intro/public/avatars/chibi
opencut render my.project.json --burn-subtitles
```

`bun run lesson ...` is the same as `node scripts/lesson.ts ...` (it runs on **Node 22+**: Remotion's
headless browser hangs under Bun). `lesson render` writes only the video, `lesson apply <project> <video>` only
swaps the picture. `opencut_ptc.py lesson ... --visuals x.visuals.json` does it inside the PTC flow.

A scene is tied to a subtitle cue by its 0-based index (`cue`) and lasts until the next scene
(or `until_cue`). Cues no scene covers get a **keyword** scene (the cue's key word, big, with its
translation), so the screen is never empty. The first scene also covers the lead-in. Text may carry
furigana: `食{た}べる`. Items inside a scene pop in one after another.

| `template` | Fields |
|---|---|
| `title` | `title`, `subtitle?`, `badge?` |
| `grammar` | `title?`, `parts: [{text, label?, tone?}]`, `join?: "+"\|"→"`, `result?: {text, label?}`, `note?` |
| `compare` | `title?`, `left`/`right: {title, items[], tone?}` |
| `chart` | `title?`, `kind: "bar"\|"donut"`, `items: [{label, value}]`, `unit?`, `highlight?` (index) |
| `dialogue` | `title?`, `layout?: "bubbles"\|"timeline"`, `lines: [{who?, text, side?}]` |
| `image` | `title?`, `images: [{src, caption?}]` (1-3), `tone?`, `note?`. `src` is a picture next to the visuals file (PNG/JPG/SVG/WebP) or an absolute path; it is copied to `public/_lesson/` (git-ignored). Made with an image AI (Flux, Midjourney...) or drawn: mind the licence of what you use. |
| `examples` | `title?`, `items: [{text, translation?, picture?, cue?}]` (1-4), `note?`. One card per example sentence (picture + Japanese + Vietnamese); card i pops in when cue `cue + i` (or `items[i].cue`) is read. A missing picture is a warning: the card shows without it. |
| `practice` | `title?`, `question`, `options` (2-4), `answer` (index), `think?` (seconds, default 5), `explain?`. The choices pop in, a ring counts down, then the right choice turns green with a check and `explain` shows. The answer stays at least 1.5 s; a short scene shortens the countdown. |

`tone` is `pink`, `navy`, `mint`, `sun` or `sky`. Examples: `scenes/lesson-sample.visuals.json`
(every template, with made-up numbers) and `scenes/ptc-vi.visuals.json` (a real listening lesson).
Content stays inside the left/top area (`SAFE` in `src/lesson/theme.tsx`), clear of the chibi in the
right corner and the burned-in subtitles at the bottom.

### Scene changes and word-by-word subtitles

Scenes change with a 0.5 s slide, fade or wipe (cycled). Each scene is held past its end by that time, so the next one still appears on its cue.

Subtitles can be drawn here, lit word by word (karaoke), instead of by the Rust renderer:

```powershell
bun run lesson whisper-setup                      # once: whisper.cpp + base model (~150 MB) into .cache/whisper (not in git)
bun run lesson words  x.project.json              # when each token of the voice is said -> x.words.json
bun run lesson build  x.visuals.json x.project.json --captions
```

Without `x.words.json`, `--captions` spreads each cue's time over its text (kana by mora, kanji by reading, pauses at 、。). With it, Whisper's tokens give the real pace; only how far through the sentence it was counts, so Whisper mishearing the words does no harm. With `opencut_ptc.py lesson --visuals ... --karaoke` this is automatic and `--burn-subtitles` is skipped (the intro/outro lines are then not burned in). Set `WHISPER_DIR` to keep Whisper elsewhere.

### Accent stickers (Lottie)

Any authored scene may carry `"accent": "check" | "cross" | "star"` (and `"accent_at": 0.8`, seconds into the scene): a small animated sticker pops once in the top-right corner, for right/wrong answers and praise. They are plain Lottie files in `public/lottie/`, written by `scripts/make_lottie.py` (re-run it to change colours); drop in any other Lottie JSON and add its name to `accent`'s type to use it.

### Writing the scenes with Claude

```powershell
python scripts/opencut_scenes.py lessons/ch193/ch193.project.json          # Claude API -> ch193.visuals.json (ANTHROPIC_API_KEY)
python scripts/opencut_scenes.py lessons/ch193/ch193.project.json --prompt-only   # just the prompt, to paste into any Claude
bun run lesson check   ch193.visuals.json ch193.project.json               # valid? (also runs inside the script)
bun run lesson preview ch193.visuals.json ch193.project.json               # look at every scene, then edit the JSON
```

The prompt carries the template schemas, the rules (no invented chart data, furigana, short text) and every cue with its translation. A reply that fails `check` is sent back once with the errors. `opencut_ptc.py lesson --visuals auto` does it in the lesson run. The lesson text goes to the Claude API: do not use it for material you may not send.

## A lesson from a script (semi-automatic)

Write the lesson first (the `soan-bai-video` skill does it with Claude Code): a script
`x.script.vi.txt` (`[1] 日本語 // Tiếng Việt`, `## Chapter` lines, `[pause=5000]`), the scenes
`x.visuals.json` and the pictures its `examples` cards name. Look it over, then:

```sh
node apps/intro/scripts/lesson.ts check x.visuals.json x.script.vi.txt     # scenes fit the script?
python scripts/opencut_ptc.py lesson --script x.script.vi.txt --out lessons/x \
    --karaoke --mascot apps/intro/public/avatars/chibi --render             # voice, scenes, chibi, video
python scripts/lesson_audio.py mix lessons/x/x.mp4 -o lessons/x/x.final.mp4 \
    --markers lessons/x/x.markers.json                                       # music (ducked), chimes, -16 LUFS
python scripts/lesson_qc.py video lessons/x/x.final.mp4                      # size, codec, loudness
node apps/intro/scripts/lesson.ts words lessons/x/x.project.json             # Whisper listens to the voice ...
python scripts/lesson_qc.py pron lessons/x/x.project.json [--fix]            # ... lines that sound off; --fix teaches textts the readings
node apps/intro/scripts/lesson.ts preview x.visuals.json lessons/x/x.project.json -o lessons/x/stills
python scripts/lesson_qc.py layout lessons/x/stills                          # text outside the safe area?
node apps/intro/scripts/lesson.ts thumbnail lessons/x/x.thumb.json           # 1280x720 PNG: title, badge, chibi pose
node apps/intro/scripts/lesson.ts short x.visuals.json lessons/x/x.project.json --grammar 13   # vertical Short, < 60 s
```

Voices come from `scripts/lesson_voices.json` (role 1 まい, 2 fumifumi, 3 花音; change the
voice ids to yours). `textts` must run with ffmpeg on its PATH, or it answers HTTP 500 and writes
empty MP3s. The music and sounds in `assets/audio/` are synthesised by `lesson_audio.py make`
(CC0, see `assets/audio/CREDITS.md`); `--bgm FILE` uses a recorded track instead.
Pictures made with an image AI stay out of git (`scenes/images/*.png`).

## Avatars

An avatar is a folder in `public/avatars/` with an `avatar.json` and one
image per layer, all the same size and stacked: `body` (the character
without a face), `eyes_open` / `eyes_closed`, and a mouth for each of
`a i u e o n` (`n` is the closed mouth). Layers are PNG or SVG with a
transparent background; each one is drawn where it sits on the face.

A **rigged** avatar moves in parts, like a VTuber: `rig` in `avatar.json`
names `hair_back` (sways a beat behind), `torso`, `head` (tilts about the
`neck` point, eyes and mouth with it) and one `arms` picture per gesture.
A scene picks gestures over time:

```json
"gestures": [{ "at": 0, "gesture": "explain" }, { "at": 2.6, "gesture": "point" }, { "at": 5.2, "gesture": "tip" }]
```

(`at` is seconds into the speech). `eyes_happy`, when the avatar has it,
is her smile once she has finished speaking.

`demo` (original SVG art) and `izumi` (the owner's own character, a rigged PNG set) are in
the repository. Put an avatar made from someone else's art in `public/avatars/` and
add it to `.gitignore` if it should stay out of git.

### 3D (VRM) and Live2D avatars

Besides layered pictures an avatar folder can hold a model; `avatar.json` then
names it instead of `layers`/`rig`:

```json
{ "name": "…", "size": [1, 1], "vrm": { "file": "model.vrm", "camera": [0, 1.3, 2.2], "target": [0, 1.18, 0] } }
{ "name": "…", "size": [1, 1], "live2d": { "file": "Hiyori.model3.json", "zoom": 1.9, "center": [0.5, 0.84] } }
```

Mouth, blinking, nodding and (VRM) gestures follow the voice exactly as for
the 2D rig; physics (swaying hair) is not run, since every frame is drawn on
its own. Try them with the samples, which are fetched rather than kept in git:

```sh
bun run scripts/fetch-vrm-sample.ts       # pixi's sample VRM, VRM Public License 1.0
bun run scripts/fetch-live2d-sample.ts    # Live2D's Cubism Core + the Hiyori sample model
bun run speak scenes/n4-teshimau-vrm.json && bun run render scenes/n4-teshimau-vrm.props.json
bun run speak scenes/n4-teshimau-live2d.json && bun run render scenes/n4-teshimau-live2d.props.json
```

Live2D: the Cubism Core is Live2D's proprietary code and a business with
annual revenue over 10 million JPY needs a Cubism SDK Release License to
publish content made with the SDK. Check https://www.live2d.com/en/sdk/license/
before releasing lessons with it. Your own models go in their own folder
under `public/avatars/`.

AivisSpeech reports no mora lengths, so `speak` spreads the moras over the
stretch where the voice really speaks (found in the wav); VOICEVOX's own
timing is used as is.

## Licence

Remotion is free for individuals and companies of up to three people; see
its licence for larger teams.
