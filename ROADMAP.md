# OpenCut IMEJI: Lộ trình phát triển

Cập nhật: 2026-11-20. Tài liệu tổng cho các phiên làm việc sau. Trạng thái chi tiết từng phiên nằm ở [lessons/HANDOFF_OpenCut_IMEJI.md](lessons/HANDOFF_OpenCut_IMEJI.md).

## 1. Định vị

OpenCut IMEJI là **xưởng sản xuất video bài giảng tiếng Nhật tự động (headless video factory)**, không phải video editor.

Luồng mục tiêu: QBank / kịch bản → textts (giọng + SRT + timeline) → cảnh minh họa → nhạc nền/SFX → render → QC → đăng YouTube (có cổng duyệt của người).

Không làm: video editor GUI, plugin system, Editor API. `apps/desktop` (GPUI), `apps/web` (editor) và `apps/api` (stub Cloudflare) đã bị xóa khỏi nhánh (còn trong lịch sử git, commit trước khi xóa: `d356565b`).

## 2. Hiện trạng (tóm tắt)

- **Lõi Rust**: `crates/media` (FFmpeg, OpenH264), `crates/project` (model, phụ đề, furigana, textts, mascot), `crates/render`.
- **CLI `opencut`** (`apps/cli`): probe, frame, thumbnails, import-textts, mascot, check, render, render-batch, env, h264, mcp (12 tool MCP).
- **Intro/cảnh** (`apps/intro`, Remotion): avatar Izumi và chibi 36 tư thế, lồng tiếng AivisSpeech, cảnh lesson (title, grammar, compare, chart, dialogue, practice), bản Shorts dọc, thumbnail (`Thumbnail.tsx`).
- **Pipeline Python** (`scripts/`, chỉ dùng standard library): `opencut_ptc.py`, `opencut_scenes.py` (Claude sinh cảnh), `lesson_audio.py`, `lesson_qc.py` (pron, engine, layout, video; circuit breaker, quarantine), `homographs.py` (5 từ tĩnh), `lesson_jobs.py` (hàng đợi HTTP, bộ nhớ/file), `publish_youtube.py` (có publish gate: cần QC PASSED).
- **Nhánh hiện tại**: `feat/ducking-fugashi-encoder` (PR #32, đã merge). Cây làm việc sạch trước phiên Cổng 1.

## 3. Quyết định đã chốt

| Quyết định | Lý do |
|---|---|
| Định vị headless factory, đóng băng GUI/editor | Editor là bài toán lớn không nằm trong mục tiêu |
| Giữ Whisper trong QC (`lesson_qc pron`) | Là bên thứ ba độc lập để bắt lỗi đọc. Nếu dùng TTS vừa làm timing vừa làm kiểm tra thì QC mất tác dụng |
| Giữ `scripts/` chỉ dùng standard library | Quy ước hiện tại. Dùng `jsonschema` nếu cần validate schema, không thêm Pydantic |
| Publish và merge phải có xác nhận của người | Quy ước dự án. Agent (MCP) chỉ submit, xem trạng thái, liệt kê quarantine, không tự đăng |

## 4. Lộ trình (theo thứ tự ưu tiên)

### Bước 1. Dọn repo (làm trước khi merge)
- Tách working tree thành 3 PR độc lập:
  1. Hạ tầng media/CLI: `encode.rs`, `setup.ts`, `batch.rs`, `mcp.rs`, `lesson.rs`, `main.rs`
  2. Tooling/skills AI: `.claude/`, `.agents/`, `.remotion/`, `skills-lock.json`
  3. Publish gate và Shorts: các commit `db49db11`, `76fefd5d` và thay đổi liên quan
- Xóa `apps/desktop`, `apps/web`, `apps/api`, README viết lại theo headless, bỏ step CI và task `upload-logos` (chỉ phục vụ web).
- Mục tiêu: rollback được từng phần nếu có hồi quy.
- Trạng thái: đã xóa GUI/editor và viết lại README. Tách PR: xem báo cáo của bước 1 (render-batch đã nằm ở nhánh `feat/render-batch`).

### Bước 2. Job state machine bằng SQLite + content-hash cache
- Thay trạng thái trong `lesson_jobs.py` bằng SQLite (WAL).
- Chặng: `QUEUED → TTS → SCENES → MIX → RENDER → QC → PUBLISH`, có `QUARANTINE`.
- Retry có kiểm soát, chạy lại từ đúng chặng lỗi.
- Băm đầu vào từng chặng: sửa một câu thoại hoặc đổi nhạc nền không gọi lại Claude và không render lại cảnh cũ.
- Lợi ích chi phí lớn nhất trong lộ trình; nên làm sớm.

### Bước 3. Quota YouTube và lịch đăng
- Theo dõi quota (mặc định 10.000 units/ngày; `videos.insert` ~1.600 units, tối đa ~6 video/ngày).
- Hàng đợi hẹn giờ (scheduled publish) thay vì đẩy đồng loạt.
- Kiểm tra trạng thái audit của OAuth project: chưa audit thường bị giới hạn upload ở chế độ private.
- Cần OAuth client thật do người dùng cung cấp để thử.

### Bước 4. Kiểm tra nguồn timing từ textts
- Xác định textts/`.timeline.json` có mốc theo mora hoặc từ không, và độ chính xác ra sao.
- Quyết định: dùng timing của textts cho phụ đề word-by-word và visemes, hay giữ Whisper.
- Dù quyết định thế nào, Whisper vẫn giữ trong QC.

### Bước 5. Structured Outputs cho cảnh do Claude sinh
- `opencut_scenes.py`: ép đầu ra theo JSON Schema `SceneSpec`.
- Validate; nếu sai cấu trúc hoặc thiếu cue, gửi lỗi về cho Claude sửa tối đa 2 lần, rồi đưa vào `QUARANTINE`.
- Schema một nguồn: sinh từ `crates/project` (schemars), validate bằng `jsonschema` ở Python và Zod ở TypeScript. Làm sau khi schema ổn định, không làm trước.

### Bước 6. Tiếng Nhật
- Thay `homographs.py` (5 từ tĩnh) bằng bộ phân tách ngữ cảnh (MeCab/UniDic hoặc chuẩn hóa cách đọc trước TTS).
- Bộ đánh giá: 市場, 十分, 人気, 一日, 辛い, cộng các từ trong `homographs.py`. Đo trước khi áp dụng rộng.

### Bước 7. Shorts và thumbnail
- Chuẩn hóa vùng an toàn cho Shorts (khoảng 20% dưới và dải cạnh phải tránh chữ/mascot).
- Gọi `renderStill` (`Thumbnail.tsx`) từ job, đồng bộ pose mascot và nhãn N5–N1.

### Bước 8. Media: gộp audio và encoder
- Gộp trộn nhạc nền/SFX và auto-ducking (giảm 18–24 dB khi có giọng) vào một đồ thị filter FFmpeg cuối cùng, tránh re-encode nhiều lần.
- Thêm encoder phần cứng (`h264_nvenc`, `h264_amf`) như tùy chọn nội bộ.
- Chỉ làm sau khi đo: con số "nhanh 3–5 lần" chưa được kiểm chứng; encoder phần cứng thường tốn bitrate hơn ở cùng chất lượng.
- `libx264` là GPL: xem lại `NOTICES.md` và cách phân phối binary trước khi dùng.

### Bước 9. Dashboard vận hành và MCP
- Dashboard vận hành là một app mới, nhẹ (không phải `apps/web` cũ đã xóa), đọc SQLite của job: xem tiến độ, mở job QUARANTINE, nghe đoạn lỗi `pron`, nhập override cách đọc, chạy lại từ bước TTS. Chưa có quyết định về công nghệ.
- MCP (`apps/cli`) bổ sung: `submit_lesson_job`, `get_job_status`, `list_quarantine`. **Không** thêm tool đăng trực tiếp; bước duyệt publish do người thực hiện qua dashboard hoặc xác nhận riêng.

## 5. Việc chưa rõ, cần kiểm tra

- textts có trả mốc thời gian chi tiết không (bước 4).
- Trạng thái audit YouTube OAuth (bước 3).
- Hiệu năng encoder phần cứng trên máy thật (bước 8).
- Tác động giấy phép `libx264` (bước 8).
- Chất lượng MeCab/UniDic trên bộ từ mẫu (bước 6).

## 6. Liên kết

- Trạng thái và bẫy vận hành: [lessons/HANDOFF_OpenCut_IMEJI.md](lessons/HANDOFF_OpenCut_IMEJI.md)
- Hướng dẫn cài Windows: [HUONG-DAN-WINDOWS.md](HUONG-DAN-WINDOWS.md)
- Pipeline bài giảng: `scripts/opencut_ptc.py`, `scripts/lesson_jobs.py`, `scripts/lesson_qc.py`

## 7. Trạng thái các bước (cập nhật sau phiên này)

- **Bước 1**: xong (PR #21, #22, #23 đã merge).
- **Bước 2**: xong. SQLite, hash theo stage, tách tts/scenes/render, quarantine và `accept`, `retry {"force": true}`, cache theo câu cho bước nghe lại.
- **Bước 3**: xong. Upload, quota theo ngày Pacific, `waiting_quota`, `--publish-at`. Đã đăng nhập OAuth thật.
- **Bước 4**: quyết định giữ Whisper cho timing từ/chữ. textts chỉ có mốc theo câu.
- **Bước 5**: xong. SceneSpec qua `submit_scenes`, kiểm tra schema và `lesson check`, sai sau 2 lượt thì quarantine.
- **Bước 6**: fugashi là bộ đọc thứ hai. `homograph_suggest.py` gợi ý mọi từ Hán chưa có furigana (không chỉ 5 từ có quy tắc), ghi file cho người duyệt, không tự sửa. Chạy fugashi cần Python có wheel (3.10), đặt `OPENCUT_TAGGER_PYTHON`.
- **Bước 7**: xong. Thumbnail nối vào job; vùng an toàn Shorts trong `apps/intro/src/lesson/shorts.ts`.
- **Bước 8**:
  - Ducking: nhạc giảm 21,8 dB khi có giọng (sidechain threshold 0,015, ratio 20), trong mục tiêu 18–24 dB. Đo bằng `measure_ducking.py`.
  - Encoder mặc định: `h264_mf` (MediaFoundation, nhanh, PSNR 55 dB ở 2 Mbps). `h264_amf` chưa dùng được (PSNR ~38 dB). `libx264` không có trong bản FFmpeg đang dùng.
  - Gộp audio và ducking đã là một đồ thị FFmpeg, video copy.
- **Bước 9**: xong. MCP `submit_lesson_job`, `get_job_status`, `list_quarantine`; dashboard `/dashboard`; nghe đoạn bị flag và nhập cách đọc cho textts (`pron_review.py`). Cố ý không có tool đăng video.

## 8. Giai đoạn kiểm định: 4 cổng (từ 2026-11-20)

Không mở roadmap tính năng mới. Mỗi giai đoạn chỉ mở khi cổng trước đạt tiêu chí bằng số liệu thật.

### Cổng 1. Đóng băng và khóa an toàn
- [x] `lesson_jobs.py`: mặc định bind `127.0.0.1`. Bind ra ngoài loopback bắt buộc có `LESSON_JOBS_TOKEN`, nếu không server từ chối khởi động (exit 2). POST (submit, retry, accept, readings, cancel, publish) cần `Authorization: Bearer <token>` khi có token. Dashboard hỏi token một lần, giữ trong `sessionStorage`. Test: `scripts/test_lesson_jobs.py` (22 test).
- [x] `opencut env`: kiểm tra `fugashi` + từ điển trong `OPENCUT_TAGGER_PYTHON` (hoặc python PATH), `textts` đang nghe ở `TEXTTS_URL`, `h264_mf` có trong FFmpeg đã ghim.
- [ ] Merge các PR còn lại về `main` và gắn tag `v1.0-rc1`. **Chờ người dùng xác nhận**: quy ước dự án không cho agent tự merge.
- Ghi chú: GET (log job, danh sách job) vẫn mở khi bind ra ngoài. Nếu cần ẩn, mở rộng token sang GET.

### Cổng 2. Đo trên tập bài chuẩn (5–10 bài, đủ ngữ pháp, so sánh, hội thoại, luyện tập)
- [ ] Tỷ lệ SceneSpec hợp lệ ngay lần 1; tỷ lệ phải retry; số cảnh lỗi trình bày khi xem bằng mắt (tràn khung, chữ đè mascot, chuyển cảnh nhanh).
- [ ] Hiệu chuẩn QC so với tai người dạy: tỷ lệ False Positive (pron chặn nhầm) và False Negative (sai kanji bị bỏ lọt). Cần khoảng 30–50 câu có nhãn.
- [ ] `measure_ducking.py` trên bản mix có nhạc nền thật: giảm nền nằm trong 18–24 dB.
- [ ] Đọc furigana trên điện thoại (h264_mf); xem Thumbnail ở ~320 px ngang.
- [ ] Thời gian máy chạy và số phút người can thiệp (pron_review, chỉnh cảnh, duyệt publish) mỗi bài.
- Cần người dạy nghe và người chạy thật. Agent không tự làm được phần này.

### Cổng 3. Tinh chỉnh theo log Cổng 2 (chỉ sửa điểm nghẽn đã thấy)
- [ ] Ngân sách ký tự trong `scene_spec.schema.json` (độ dài tiêu đề, số dòng mỗi thẻ) nếu có lỗi tràn chữ.
- [ ] Nạp mẫu lỗi phát âm thật từ `pron_review.py` vào override, rà soát thủ công trước khi áp dụng để tránh sai lan sang bài khác. Hạ báo động giả QC.
- [ ] Thumbnail hiển thị cạnh nút Publish trên dashboard, kèm kiểm tra kỹ thuật (độ phân giải, chữ không cắt mép). Không chấm thẩm mỹ bằng AI.
- [ ] Encoder: chỉ biên dịch libx264 nếu Cổng 2 cho thấy h264_mf làm mờ furigana.

### Cổng 4. Mở rộng sản lượng (sau khi Cổng 3 ổn định)
- [ ] Cắt Shorts 9:16 tự động từ bài dài, dùng chapters và cảnh ngắn có sẵn (grammar, compare, practice 30–50 giây).
- [ ] Đóng gói môi trường: tự động hóa `OPENCUT_TAGGER_PYTHON`.
- [ ] Vòng phản hồi YouTube sau 10–20 video: CTR Thumbnail, tỷ lệ giữ chân 30 giây đầu, điều chỉnh Intro và mẫu Thumbnail.

Việc tùy chọn còn lại từ trước: đo `pron` trên bài thật và kiểm tra ducking trên bài có nhạc nền (đã nằm trong Cổng 2).
