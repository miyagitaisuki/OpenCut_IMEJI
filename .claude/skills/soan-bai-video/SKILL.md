---
name: soan-bai-video
description: Dùng khi người dùng nhờ soạn một video bài giảng tiếng Nhật theo bài Minna no Nihongo (hoặc một chủ đề ngữ pháp) cho xưởng OpenCut IMEJI: viết kịch bản textts (Nhật + furigana + dịch Việt) và file cảnh visuals.json, kiểm bằng `lesson check`, rồi dừng chờ người dùng duyệt trước khi lồng tiếng. Trigger: soạn bài video, video bài Minna, kịch bản bài giảng, /soan-bai-video.
---

# Soạn video bài giảng (kịch bản + cảnh)

Đầu ra trong `lessons/<ten>/` (đã gitignore):
- `<ten>.script.vi.txt`: kịch bản textts, mỗi câu một dòng `[vai] câu tiếng Nhật // bản dịch Việt`.
- `<ten>.pictures.md`: danh sách hình cần tạo (tên file + prompt tiếng Anh, chung một khối "Phong cách chung"), để người dùng tạo bằng Gemini (Google AI Pro) rồi đặt vào `lessons/<ten>/images/`. Mẫu: `apps/intro/scenes/minna-05.pictures.md`.
- `<ten>.visuals.json`: cảnh minh họa, `cue` = số thứ tự dòng nói (0 = dòng nói đầu tiên; dòng `[pause=...]` và dòng `#` không tính).

Sau đó **dừng lại** để người dùng duyệt. Không gọi textts và không render khi chưa được duyệt.

## 1. Hỏi nhanh (chỉ hỏi phần chưa rõ)
Hỏi số bài Minna (hoặc chủ đề), cấp độ (mặc định N5 với bài 1–25, N4 với bài 26–50), độ dài (mặc định 5–8 phút ≈ 50–80 câu), và có câu hỏi QBank để dùng lại hay không (dùng `mcp__qbank__list_questions` nếu có).

## 2. Cấu trúc bài (theo thứ tự)
1. **Mở bài** (2–3 câu): chào, giới thiệu chủ đề bài. Cảnh `title` (badge `N5`/`N4`).
2. **Từ vựng chính** (5–8 từ): mỗi từ một câu có ví dụ ngắn. Dùng cảnh `compare` hoặc `image`, hoặc để cảnh từ khóa mặc định.
3. **Ngữ pháp**: mỗi mẫu câu gồm câu giới thiệu + ví von (cảnh `grammar`), rồi **ít nhất 3 câu ví dụ, mỗi câu một dòng** (cảnh `examples`: mỗi thẻ có hình `images/<ten-hinh>.png` + câu Nhật + dịch Việt, thẻ hiện lên đúng lúc câu đó được đọc; mỗi hình một dòng trong `pictures.md`). Dùng `compare` khi so hai mẫu dễ nhầm.
4. **Hội thoại mẫu** (6–10 câu, 2 vai): cảnh `dialogue` (bubbles).
5. **Luyện tập** (3–5 câu hỏi): mỗi câu hỏi gồm 1 dòng đọc câu hỏi, 1 dòng `[pause=5000]`, 1 dòng đọc đáp án và lý do. Cảnh `practice` (`think` 5 s) đặt ở dòng đọc câu hỏi, `until_cue` đến hết dòng đáp án.
6. **Tổng kết + rủ học bài sau cùng cô Izumi** (2–3 câu; không nhắc QBank). Cảnh `title` hoặc `grammar` tóm tắt, kèm `accent: "star"`.

## 3. Quy tắc nội dung
- Lời giảng **toàn tiếng Nhật**, đúng trình độ: N5 dùng thể です/ます, câu ngắn ≤ 40 ký tự, chỉ dùng từ đã học tới bài đó; giải thích ngữ pháp bằng câu đơn giản.
- **Giải thích dễ hiểu cho người chưa biết gì**: mỗi mẫu ngữ pháp có **một phép ví von sinh động, gần đời sống** (vd. trợ từ へ là "mũi tên chỉ hướng", で là "chiếc xe chở hành động", と là "nắm tay đi cùng"), nói bằng tiếng Nhật dễ, rồi minh họa ngay bằng cảnh (`grammar` có `note` nhắc lại ví von, hoặc `image`/`compare`). Không dùng thuật ngữ ngữ pháp khi chưa giải thích; đi từ ví dụ → quy tắc, không đi ngược lại. Mỗi ý chỉ một bước nhỏ, nhắc lại ví von ở phần tổng kết.
- **Chữ trên slide**: phần giải thích (tiêu đề cảnh, `label`, `note`, `explain`, tiêu đề cột `compare`, `subtitle`) viết **tiếng Việt**, ngắn; phần **ví dụ, mẫu câu, từ vựng, câu hỏi và lựa chọn luyện tập** giữ **tiếng Nhật** có furigana. Lời đọc (kịch bản) vẫn toàn tiếng Nhật.
- **Furigana cho mọi chữ Hán** theo cú pháp textts `漢字{かんじ}`, kể cả trong `visuals.json`.
- **Câu ví dụ tự viết**, không chép nguyên văn hội thoại, bài tập hay ví dụ trong sách Minna (bản quyền). Được dùng tên mẫu ngữ pháp và từ vựng của bài.
- Vai (giọng textts cố định): `[1]` **まい** (giáo viên, lời giảng), `[2]` **fumifumi** (học sinh nam), `[3]` **花音** (học sinh nữ). Hội thoại mẫu dùng `[2]`/`[3]`; trong cảnh `dialogue`, `who` ghi tên vai (ふみ, 花音{かのん}).
- Bản dịch Việt tự nhiên, ngắn; giữ đúng một bản dịch cho mỗi dòng nói.
- Mỗi câu ≤ 60 ký tự (không tính furigana) để phụ đề vừa hai dòng.
- Cảnh: xoay vòng mẫu, không lặp cùng mẫu liền nhau. Cảnh chỉ dùng nửa trên màn hình, nên chữ phải ngắn: `compare` ≤ 5 mục, `dialogue` ≤ 5 dòng mỗi cảnh (hội thoại dài thì chia nhiều cảnh).

## 4. Kiểm
```bash
cd apps/intro
node scripts/lesson.ts check ../../lessons/<ten>/<ten>.visuals.json ../../lessons/<ten>/<ten>.script.vi.txt
```
Sửa đến khi không còn `error`. Cảnh báo về furigana hoặc câu dài thì sửa trừ khi có lý do. Muốn xem tham chiếu các mẫu cảnh thì chạy `node scripts/lesson.ts prompt <script.vi.txt>`.

Rồi tự soát (hoặc giao một agent độc lập soát): ngữ pháp, cách đọc furigana, bản dịch, và đáp án luyện tập có đúng một đáp án đúng không.

## 5. Bàn giao để duyệt
Báo đường dẫn hai file, số câu, thời lượng ước tính (≈ 5 s/câu + các pause), danh sách cảnh (cue → mẫu). Hỏi: **Duyệt và lồng tiếng (Đề xuất)** / Sửa. Chỉ khi người dùng duyệt mới dựng video. Chuẩn bị: textts REST chạy kèm ffmpeg trong PATH (không thì HTTP 500, MP3 rỗng), AivisSpeech bật, hình đã nằm trong `images/`. Dòng `## Tên chương` trong kịch bản là chương YouTube (cần ≥ 3).

```bash
python scripts/opencut_ptc.py lesson --script lessons/<ten>/<ten>.script.vi.txt --out lessons/<ten>     --karaoke --mascot apps/intro/public/avatars/chibi --render
python scripts/lesson_audio.py mix lessons/<ten>/<ten>.mp4 -o lessons/<ten>/<ten>.final.mp4 --markers lessons/<ten>/<ten>.markers.json
python scripts/lesson_qc.py video lessons/<ten>/<ten>.final.mp4
node apps/intro/scripts/lesson.ts words lessons/<ten>/<ten>.project.json && python scripts/lesson_qc.py pron lessons/<ten>/<ten>.project.json --fix
node apps/intro/scripts/lesson.ts thumbnail lessons/<ten>/<ten>.thumb.json
node apps/intro/scripts/lesson.ts short lessons/<ten>/<ten>.visuals.json lessons/<ten>/<ten>.project.json --grammar <cue>
```

`pron --fix` báo dòng nghe lệch bản viết và thêm cách đọc vào từ điển textts; có lệch thì lồng tiếng lại. Giao agent độc lập soát ngữ pháp/dịch (`<ten>.review.md`) trước khi lồng tiếng. Đăng YouTube (unlisted, playlist) chỉ khi người dùng đồng ý sau khi xem bản cuối: `publish_youtube.py ... --dry-run` trước.

Mẫu: `apps/intro/scenes/minna-05.script.vi.txt` + `minna-05.visuals.json`.
