# HANDOFF: Izumi Live2D rig (OpenCut intro)

- Cập nhật: 2026-11-21 · Phiên bản: 3 (xem mục 11: hướng mới là visual novel dạng video, KHÔNG dùng Cubism nữa)
- Repo: `miyagitaisuki/OpenCut_IMEJI`, branch `claude/sharp-ritchie-fgr2gi`. Chưa commit gì cho project này. Mọi file làm việc nằm ngoài repo (scratchpad).

## 1. Mục tiêu & phạm vi
- Làm bộ vector rig Live2D cho nhân vật Izumi (chibi, nhìn thẳng), để dùng trong `apps/intro` (Live2dAvatar.tsx đọc `.model3.json` từ `public/avatars/izumi/`).
- Trong phạm vi: tách/chuẩn hóa art, PSD layer, brief cho người vẽ/tạo ảnh, tiêu chí miệng lip-sync.
- Ngoài phạm vi (hiện tại): rig trong Cubism Editor (phải làm trên máy người dùng; môi trường này không có GUI), tạo ảnh bằng Gemini (môi trường không có API key và proxy chặn host).

## 2. Quyết định đã chốt
- Phong cách: chuyển toàn bộ sang flat vector, người dùng chấp nhận compromise (ảnh lẫn phong cách, lật ngang cặp trái/phải từ một bản).
- Trái/phải theo nhân vật (bên trái nhân vật = bên phải ảnh).
- Mắt: tách Iris và White; mắt nhắm (`EyeClosed`) là layer riêng, mặc định ẩn.
- Lông mày: chọn cặp 1 (`BrowL`/`BrowR`).
- Tóc: `HairTail` = đuôi tóc mai dài; `HairSide` = tóc mai ngắn; `HairFront` = tóc mái.
- Lip-sync: **phương án A**, một bộ miệng có tham số `ParamMouthOpenY` và `ParamMouthForm`, khớp `Live2dAvatar.tsx`. Bảng keyform theo mora: あ(1.00,0.30), い(0.30,1.00), う(0.35,-1.00), え(0.55,0.70), お(0.75,-0.70), ん/っ/pause/ま ば ぱ (0,0).
- Miệng: vẽ **một hình** (môi + phần trong) rồi tách 3 layer, để tránh chồng lớp.
- Kích thước miệng: 0.14–0.25 chiều rộng mặt. Con số "300 px" trong brief v1 là SAI, đã bỏ.
- Canvas 2400×2800, gốc (0,0), mặt tâm (1200,1050), rộng ~900 px.
- Thứ tự lớp (dưới → trên, 31 layer) theo `izumi-rig-brief.md` mục 6.

## 3. Đã làm xong
- Brief tổng: `izumi-rig-brief.md` (31 file, canvas, thứ tự lớp, checklist).
- Brief miệng: `mouth-option-a-v2.md` (bản hiện hành; v1 `mouth-option-a.md` đã lỗi thời).
- Brief lỗi chung: `lipsync-and-fixes.md`.
- Brief sửa tóc/trán: `hair-forehead-fixes.md`.
- PSD: nhiều bản; bản mới nhất có ý nghĩa là `izumi-rig-v8.psd` (tên layer sạch). `v8` = bản v7 + median thử trên `HairBack`, KHÔNG phải bản cuối. Nguồn gốc: upload `9c970978-izumi-rig.psd` → v7.
  - Thư mục: `scratchpad/review/` (v7, v8) và `scratchpad/izumi_parts/` (art đã tách).
- Miệng mở đã có trong PSD (`Mouth_Inside` 16.783 px, có răng và lưỡi). Layer `Tie` không còn khối đặc. `Book` đã chỉnh về palette. `EyeClosedL/R` ẩn mặc định.

## 4. Đang làm dở / còn lỗi (đã xác nhận trên v8; trạng thái mới nhất ở mục 10)
1. **Chồng lớp miệng:** môi trên che răng, môi dưới tạo viền kép. Nguyên nhân: miệng mở và môi vẽ từ hai nguồn khác nhau. Sửa theo `mouth-option-a-v2.md` (vẽ một hình rồi tách).
2. **Hạt tối sau cằm** (`HairBack`, một phần `HairSide`): chưa sạch, đang là mảng nâu loang. Median chỉ là tạm.
3. **Khe sáng trên trán bên trái:** `Face` lộ da do `HairFront` không phủ hết chân tóc. Có hai cách sửa trong `hair-forehead-fixes.md`.
4. **Mũi quá nhỏ:** `Nose` chỉ rộng 16 px, gần như không thấy. CHƯA XỬ LÝ, chưa có brief riêng.
5. **Mắt:** `EyelashL_Upper`/`R_Upper` có khối đặc (~36% bbox). Chưa xử lý.
6. **Cà vạt:** chưa đạt hoàn toàn sau khi làm sạch (còn một phần đặc). Có thể cần xuất lại.
7. Trọng số vị trí: toàn bộ vị trí layer trong PSD là ƯỚC LƯỢNG, chưa căn chỉnh kỹ, cần kiểm tra lại khi rig.

## 5. Việc cần làm tiếp (theo thứ tự)
1. Người dùng chạy prompt miệng mở một hình (`mouth-option-a-v2.md` mục 5) và gửi lại ảnh.
2. Người dùng sửa tóc/trán theo `hair-forehead-fixes.md`, hoặc xuất lại tóc/`Face` dạng flat.
3. Gửi art mới cho assistant: tách thành 3 layer miệng, sửa mũi, ghép vào PSD → v9.
4. Kiểm tra lại v9 theo checklist (không chồng lớp, không khe sáng, không hạt).
5. Chuyển PSD sang người rig trong Cubism Editor, tạo mesh + deformer + tham số, xuất `.cmo3`/`.can3` và `.model3.json`.
6. Đặt vào `apps/intro/public/avatars/izumi/` và kiểm tra tham số khớp `Live2dAvatar.tsx`.

**Bước đầu tiên session sau:** xác nhận người dùng đã có ảnh miệng mở mới chưa; nếu có, tách và ghép thành v9.

## 6. Câu hỏi/điểm chưa chốt
- Ai rig trong Cubism: người dùng, người khác, hay tự động? (chưa rõ)
- Kiểm tra điều khoản Live2D Cubism Editor/Core cho video công khai cho sinh viên (chưa kiểm tra).
- Có chấp nhận mũi nhỏ như hiện tại không, hay cần vẽ lại?
- Có giữ compromise phong cách lẫn lộn (tóc/mặt tranh; thân/tay phẳng) hay vẽ lại để thống nhất hoàn toàn?

## 7. Lỗi đã gặp & bẫy cần tránh
- psd-tools ghi tên layer có ký tự `\x00` nếu không xóa. Phải `name.strip('\x00')` và đặt `layer.name` sau khi tạo.
- `PixelLayer.frompil(..., layer_name=...)` không đặt tên đúng; phải gán `layer.name` riêng.
- Mọi layer trong PSD đang là canvas đầy đủ (0,0,2400,2800); vị trí thực nằm trong pixel. Khi đặt mới, dùng `left/top`.
- Tách art từ ảnh xanh lá: nếu bỏ qua kiểm tra alpha có thể lấy nhầm nền. Kiểm tra `fill` (tỉ lệ pixel đặc trong bbox): fill ~0.99 là dấu hiệu khối chữ nhật nhầm.
- Tạo ảnh bằng công cụ AI cho nhiều bộ phận: mỗi lần sinh ra một kích thước/tư thế khác. Phải đối chiếu lại tỉ lệ với mặt.
- Gộp môi và phần trong miệng từ hai nguồn khác nhau sẽ chồng lớp (đã gặp).

## 8. Nguồn & tài liệu tham chiếu
- Code: `apps/intro/src/Live2dAvatar.tsx` (tham số `ParamMouthOpenY`, `ParamMouthForm`, `ParamEyeLOpen`, `ParamEyeROpen`, `ParamAngleX/Y/Z`, `ParamBodyAngleX/Z`, `ParamBreath`, `ParamCheek`, `ParamEyeLSmile`, `ParamEyeRSmile`). `apps/intro/src/visemes.ts` (vowel → Mouth: a,i,u,e,o,n).
- Tham chiếu nhân vật: ảnh reference chibi do người dùng cung cấp (tệp `images/1.webp`... trong upload).
- Không có nguồn bên ngoài nào được xác nhận. Các thông số Live2D khác [CẦN NGUỒN].

## 9. Thông tin kỹ thuật
- Stack: Remotion (intro app), Live2D qua `pixi-live2d-display-advanced` (`pixi.js` 7.4.2). Cubism Core không commit (điều khoản Live2D).
- Python: `psd-tools` 1.27.0, `scipy`, `Pillow`, `numpy` (đã cài trong phiên).
- Không có biến môi trường bí mật nào được dùng trong project này.
- Lệnh render intro: `bun run render` (trong `apps/intro`), theo README.

## 10. Cập nhật phiên bản 2 (trạng thái mới nhất)

**Bản cuối đã chọn:** `izumi-rig-final.psd`, lấy từ upload `d2de3d30-izumi-rig.psd`. 31 layer, tên đã sạch, thứ tự đúng brief. Đây là file dùng để import vào Cubism Editor.

**Đã làm trong v2:**
- Miệng: thay bằng bản vẽ đơn giản, nhỏ (rộng ~108 px). Không còn chồng viền. Đã thử vẽ bằng code, kết quả thô, nên bản cuối dùng art từ upload.
- Tạo `cubism-setup-izumi.md`: nhóm Parts, thứ tự vẽ, tham số (ParamAngleX/Y/Z, ParamEyeLOpen/ROpen, ParamEyeLSmile/RSmile, ParamMouthOpenY/Form, ParamBodyAngleX/Z, ParamBreath, ParamCheek), keyform miệng, mắt chớp, checklist xuất file.
- Đã xuất `izumi-rig-final.psd` và `cubism-setup-izumi.md` cho người dùng.

**Lỗi còn trong bản cuối (chưa sửa):**
1. Hạt tối sau cằm trong `HairBack` (không ảnh hưởng rig, hiện trên khung).
2. Khe sáng trên trán bên trái (`Face` lộ qua `HairFront`).
3. `Nose` chỉ rộng 16 px, gần như không thấy.
4. Lông mi trên `EyelashL_Upper`, `EyelashR_Upper` có khối đặc.
5. Vị trí layer là ước lượng, cần kiểm tra khi đặt mesh trong Cubism.

**Đã sai ở brief cũ:** "miệng tối thiểu 300 px" (`mouth-option-a.md`). Đúng là 0.14–0.25 chiều rộng mặt. Brief hiện hành là `mouth-option-a-v2.md`.

**Việc chưa làm và đang chờ:**
- Bạn import `izumi-rig-final.psd` vào Cubism Editor, tạo mesh, deformer, tham số, rồi xuất `.moc3`, `.model3.json`, texture vào `apps/intro/public/avatars/izumi/`. Môi trường này không chạy được Cubism nên mình không làm được bước này.
- Sau khi xuất: gửi lại để kiểm tra tên tham số khớp `Live2dAvatar.tsx`.

**Quyết định còn mở:** ai rig trong Cubism; có sửa mũi không; có giữ phong cách lẫn lộn không; điều khoản Live2D cho video công khai cho sinh viên (chưa kiểm tra).

**Bước đầu tiên session sau:** xác nhận bạn đã import PSD vào Cubism chưa. Nếu đã xuất model, kiểm tra tên tham số; nếu chưa, hỏi có muốn sửa mũi/hạt tóc trước khi rig không.

## 11. Cập nhật phiên bản 3 (hướng hiện tại)

**Đổi hướng:** không dùng Cubism/Live2D nữa. Mục tiêu mới là **visual novel dạng video** cho bài học OpenCut: sprite PNG (nửa thân, từ thắt lưng trở lên), khung hội thoại, tên nhân vật, lựa chọn, render bằng Remotion ra MP4. Người dùng đã chọn hướng này (đánh giá: tận dụng `dialogue`, `practice`, `PoseAvatar`, `opencut mascot`, `opencut render`). Khi phiên mới bắt đầu, KHÔNG nhắc lại Cubism trừ khi người dùng hỏi.

**Cần bổ sung cho dựng cảnh (chưa có):** trường `expression` cho từng dòng thoại; template `sprite` + `background`; khung tên/thoại kiểu VN; lựa chọn có kết quả đúng/sai (video không rẽ nhánh); lip-sync bằng lớp miệng (6 hình あいうえおん) hoặc chuyển động thân nếu không có miệng.

**Đã có trong `scratchpad/`:**
- Sprite cắt từ thắt lưng (y=700): `sprites/angry_arms_crossed.png`, `wave_book.png`, `smile_hug_book.png`, `shy_hug_book.png` (606×660, trong suốt).
- Tách nền ô vuông (images 9–13): `cutout/s9..s13_clean.png`, còn sót ô vuông ở mép tóc.
- Base mặt trống nền trắng (images 14–18, flood-fill từ mép): `base/14..18_cut.png`. Còn vệt trắng trong mép tóc, một vệt xám trên trán ảnh 15.
- Base mặt trống khác (images 20, 21): tay vẫy và tay thõng, chưa cắt.
- Bảng biểu cảm (images 19, 22, 23): chưa dùng được. 19 và 22 có lấp lánh, 22 lưới lệch, 23 cắt theo lưới thất bại (mắt bị cắt ngang, miệng lệch ô).
- Công cụ: `tools/cut_grid.py` (cắt theo lưới 5×2, band lông mày/mắt/miệng). Đã gửi file cho người dùng. KHÔNG hoạt động tốt với bảng 23.

**Tài liệu brief đã gửi:** `brief/izumi-rig-brief.md`, `brief/mouth-option-a-v2.md`, `brief/hair-forehead-fixes.md`, `brief/cubism-setup-izumi.md` (đã lỗi thời theo hướng mới), `brief/sprite-generation.md` (biểu cảm E01–E10, cử chỉ G01–G11, trang phục O01–O03, prompt mẫu, anchor `images/7.png`), `brief/sprite-base-and-expression-layers.md` (base mặt trống + lớp biểu cảm; slot `slots.json` chưa đo).

**Quyết định đã chốt:**
- Visual novel dạng video (Remotion + MP4).
- Phong cách: chấp nhận compromise (không đồng nhất flat vector).
- Biểu cảm dùng ảnh PNG full sprite hoặc base + lớp biểu cảm; cả hai đều được chấp nhận.

**Đang chờ quyết định của người dùng:**
- Cách sinh biểu cảm: (1) mỗi biểu cảm một ảnh riêng, khung cố định, đề xuất; hoặc (2) bảng lưới có vạch ngăn.
- Có làm cảnh prototype (3–4 dòng, 2–3 biểu cảm, 1 lựa chọn) trước không.
- Mẫu giọng (speaker ID) và kịch bản mẫu chưa cung cấp.
- Có dùng base mặt trống + lớp biểu cảm hay sprite đầy đủ cho từng biểu cảm.

**Lỗi/bẫy đã gặp (bổ sung):**
- Nền ô vuông trong ảnh AI là pixel thật, không phải alpha: phải yêu cầu nền trắng/xanh đồng nhất từ đầu.
- Tách nền bằng ngưỡng màu làm mất navy và da khi ngưỡng rộng. Dùng ngưỡng hẹp (±10) và loang từ mép khi nền trắng.
- Cắt theo band cố định thất bại khi cụm chi tiết nằm sát ranh giới band.
- `psd-tools`: tên layer có `\x00`, phải strip.

**Bước đầu tiên session sau:** hỏi người dùng chọn cách sinh biểu cảm (mục đang chờ) rồi viết prompt. Nếu người dùng gửi ảnh mới, kiểm tra theo bảng ở mục 11 trước khi xử lý.
