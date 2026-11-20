# OpenCut intro — virtual idol intros

Remotion scenes in which a 2D avatar says the lesson's opening line, its
mouth following the vowels AivisSpeech (or VOICEVOX) reports for each mora:
あいうえお, closed for ん, っ, pauses and ま・ば・ぱ. She breathes, sways
and blinks, sakura petals drift, and the lesson's title is on a card
beside her.

## Make an intro

1. Write a scene, e.g. `scenes/n4-teshimau.json`:

   ```json
   {
     "scene_type": "intro",
     "avatar": "sakura",
     "subtitle": "N4 文法",
     "title": "～てしまう",
     "text": "みなさん、こんにちは。N4文法の授業へようこそ。今日は「てしまう」を勉強しましょう。",
     "translation": "Xin chào các bạn. Chào mừng đến với bài học ngữ pháp N4. …",
     "speaker": 1431611904
   }
   ```

   `speaker` is an AivisSpeech style id (the same ids as textts' `roles.yaml`);
   left out, the engine's first voice speaks. `speed` (1 = normal) and
   `colors` (`["#ffd6e4", "#2b3a67"]`, the background) are optional.

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
   ready outro (sakura points the lesson's learners to QBank): voice and
   render it exactly like an intro.

No engine at hand? `bun run scripts/mock-engine.ts` serves a stand-in on
port 10101 (a tone instead of a voice, rough mora timing) to try the pipeline.

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

`demo` (original SVG art) and `sakura` (the owner's own character, a rigged PNG set) are in
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
