# DESIGN.md — OpenCut IMEJI (đầu ra video)

Quy chuẩn hình ảnh cho video bài giảng: intro/outro (`apps/intro`), cảnh bài giảng, phụ đề, thumbnail. Repo này không có giao diện web; mọi quy tắc ở đây áp dụng cho khung hình video.

**Nguồn:** hệ thống thiết kế IMEJI (`project/tokens.css` trong artifact "IMEJI日本語教室"). Màu và font lấy từ đó; chi tiết nằm trong `apps/intro/src/lesson/theme.tsx`.

Mục **[cần quyết định]** là chỗ chưa chốt.

## 1. Màu

Map token IMEJI sang hằng số trong `C` (`theme.tsx`):

| Hằng số | Token IMEJI | Hex | Dùng cho |
|---|---|---|---|
| `navy` | primary-900 | `#1e3a8a` | Chữ tiêu đề, nền tối, nền intro |
| `navySoft` | primary-700 | `#1d4ed8` | Viền tối |
| `rose` | primary-400 | `#60a5fa` | Vạch tiêu đề, chữ đang đọc (karaoke) |
| `pink` | primary-200 | `#bfdbfe` | Thẻ, nền scene |
| `pinkSoft` | primary-50 | `#eff6ff` | Nền gradient |
| `sky` | primary-100 | `#dbeafe` | Nền scene xanh |
| `mint` | success-100 | `#d0fae5` | Nền scene xanh lá |
| `sun` | warning-100 | `#fef3c6` | Nền scene vàng |
| `ink` | slate-900 | `#0f172a` | Chữ chính |
| `muted` | slate-500 | `#526177` | Chữ phụ |
| `cream` | slate-50 | `#f8fafc` | Nền sáng |

Phụ đề và chú thích: nền `rgba(10,14,30,.78)`, chữ trắng, bản dịch `warning-300` `#ffd230`, chữ đang đọc `primary-400` `#60a5fa`.

Quy tắc:
- Chữ trắng chỉ đặt trên nền tối (`navy`, `primary-600`, nền phụ đề).
- Mọi cặp chữ/nền đạt WCAG AA ở khung 1920×1080.
- Thêm màu mới phải đi qua `C`, không viết hex rải rác trong component.

**Đã bỏ chủ đề sakura:** không còn cánh hoa rơi, mọi màu hồng đã đổi sang IMEJI. Các sticker Lottie (`scripts/make_lottie.py`, sinh lại vào `public/lottie/`) và `scenes/images/office.svg` cũng đã đổi.

**Ngoại lệ còn lại:**
- Ảnh mascot (`public/avatars/sakura/*`, PNG có tóc hồng) là tài nguyên nhân vật, không đổi bằng code. Muốn đổi thì vẽ lại.
- Dấu ✓ đúng (`Short.tsx`, `#1f8a4c`) giữ nguyên.

## 2. Chữ

| Vai trò | Font | Ghi chú |
|---|---|---|
| Phụ đề, nội dung, bảng | **Be Vietnam Pro** (`FONT`, đóng gói qua `@fontsource/be-vietnam-pro`, các trọng số 400–800) | Chữ Latin và Việt. Chữ Nhật rơi về Noto Sans CJK JP |
| Tiêu đề scene, tiêu đề intro | **Noto Serif JP** (`SERIF`) | Serif theo yêu cầu; môi trường render đã có. Rơi về Playfair Display, rồi serif hệ thống |

- Font được đóng gói trong `apps/intro`, nên render không cần tải từ mạng.
- Tiêu đề scene: 700, cỡ 52 px. Tiêu đề intro: 700, cỡ 150 px.
- Furigana giữ nguyên cách hiển thị (`Jp`).

## 3. Logo và thương hiệu

- **Không dùng logo IMEJI trong video OpenCut.** Chỉ dùng `brand/marks/` của OpenCut cho các khung có logo.
- Không dùng ảnh nền và hình minh họa của IMEJI (`assets/aistudio/*`, `assets/fb/hero.jpg`).

## 4. Chuyển động và bố cục

- Giữ nguyên hệ thống spring và `SAFE` (vùng nội dung trên, phụ đề dưới). Không đổi trong đợt này.
- Chuyển động chỉ để chỉ ra thay đổi, không trang trí thêm.

## 5. Kiểm tra trước khi merge

1. `bun run test` trong `apps/intro`.
2. Render một intro mẫu (`bun run render ...`) và xem khung đầu, khung giữa, khung cuối.
3. Kiểm tra độ đọc của phụ đề và tiêu đề trên nền mới.
4. Đối chiếu với các mục 1–4.
