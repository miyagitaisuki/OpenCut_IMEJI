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
   `--outro` adds a closing clip the same way.

No engine at hand? `bun run scripts/mock-engine.ts` serves a stand-in on
port 10101 (a tone instead of a voice, rough mora timing) to try the pipeline.

## Avatars

An avatar is a folder in `public/avatars/` with an `avatar.json` and one
image per layer, all the same size and stacked: `body` (the character
without a face), `eyes_open` / `eyes_closed`, and a mouth for each of
`a i u e o n` (`n` is the closed mouth). Layers are PNG or SVG with a
transparent background; each one is drawn where it sits on the face.

`demo` (original SVG art) is the only avatar in the repository. Avatars
made from your own art, such as `sakura`, stay out of git by default
(see `.gitignore`), since this repository is public.

## Licence

Remotion is free for individuals and companies of up to three people; see
its licence for larger teams.
