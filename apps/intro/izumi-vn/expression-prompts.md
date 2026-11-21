# Prompt sinh biểu cảm Izumi (E01–E10), mỗi biểu cảm một ảnh

Theo brief `sprite-generation.md`. Mỗi lần sinh đính kèm anchor `assets/source/7.png` làm reference.

## Thông số
- Canvas sinh: 1024 × 1024, nền trắng `#FFFFFF` (tách nền sau).
- Khung cố định: cắt ở y = 700 px từ đỉnh, nhân vật chiếm 60–65% chiều cao khung.
- Anchor `7.png` là ảnh toàn thân: prompt phải yêu cầu chỉ nửa thân, không chân.
- Đặt tên: `O01_E0x_G01.png` (O = trang phục, E = biểu cảm, G = cử chỉ tay).
- Trang phục và cử chỉ cố định ở G01 + O01 cho bộ này. Các cử chỉ khác làm sau.

## Template (dán nguyên, chỉ thay dòng `Expression`)

```
Same chibi anime girl as the reference image: same face, same brown wavy shoulder-length hair, same big brown eyes, same proportions and head size.
Upper body only, cropped at the waist. No legs visible.
Expression: {EXPRESSION}.
Hand gesture: hands at sides, relaxed.
Outfit: navy blazer uniform with white collar, blue striped tie, navy skirt hidden below the waist.
Flat clean anime style, soft colors, thin dark-brown outline, plain white background, centered, same scale as reference.
```

Negative prompt: `legs, feet, shoes, text, watermark, extra fingers, distorted hands, different hair, different face, cropped head, full body`

## Biểu cảm (dòng `Expression` của từng file)

| File | {EXPRESSION} |
|---|---|
| `O01_E01_G01.png` | neutral, mouth closed, calm eyes |
| `O01_E02_G01.png` | gentle smile, closed mouth in a small ω shape |
| `O01_E03_G01.png` | happy, open-mouth smile, sparkling bright eyes |
| `O01_E04_G01.png` | angry, furrowed brows, sharp eyes, lips pressed together |
| `O01_E05_G01.png` | sad, brows drooping, sad downturned eyes |
| `O01_E06_G01.png` | shy, blushing cheeks, eyes looking to the side |
| `O01_E07_G01.png` | surprised, eyes wide open, small round mouth |
| `O01_E08_G01.png` | worried, slightly furrowed brows, uneasy eyes |
| `O01_E09_G01.png` | thinking, eyes looking up to the upper left, lips slightly pressed. **Thêm vào prompt: "navy blazer, no sailor collar, no white sailor-style collar"** |
| `O01_E10_G01.png` | winking, one eye closed, the other open, small smile. **Thêm: "same scale and position as the reference, head centered at the same height as the reference"** |

## Cử chỉ tay (G02–G11), dùng với E01 + O01

Thay dòng `Hand gesture:` trong template. Các file đặt tên `O01_E01_G0x.png`.

| File | Dòng `Hand gesture:` |
|---|---|
| `O01_E01_G02.png` | arms crossed in front of chest, forearms folded |
| `O01_E01_G03.png` | one arm raised high, waving, open hand, the other arm relaxed |
| `O01_E01_G04.png` | hugging a red book against chest with both arms |
| `O01_E01_G05.png` | holding a red book with one hand at the side |
| `O01_E01_G06.png` | one index finger pointing up |
| `O01_E01_G07.png` | one arm extended pointing to the side (viewer's right) |
| `O01_E01_G08.png` | one thumb up, other hand at side |
| `O01_E01_G09.png` | one hand placed on chest |
| `O01_E01_G10.png` | shrugging, both palms open, shoulders raised |
| `O01_E01_G11.png` | both hands together clapping in front of chest |

## Trang phục (O02–O03), dùng với E01 + G01

Thay dòng `Outfit:` trong template. Giữ nguyên tóc và khuôn mặt.

| File | Dòng `Outfit:` |
|---|---|
| `O02_E01_G01.png` | same blazer cut in grey, white collar, grey skirt hidden below the waist |
| `O03_E01_G01.png` | white collared blouse, no blazer, navy skirt hidden below the waist |

## Kiểm tra từng ảnh (trước khi nhận)
- [ ] Khuôn mặt, tóc, tỉ lệ đầu giống `7.png`.
- [ ] Không có chân, chữ, watermark.
- [ ] Tay đủ số ngón, không méo.
- [ ] Biểu cảm đọc được ở khoảng 300 px chiều cao.
- [ ] Vị trí đầu và thân khớp với các ảnh khác trong bộ (cùng khung).
- [ ] Nếu lệch khung: ghi lại file và báo, không tự cắt tay.

## Sau khi sinh
1. Xóa nền trắng, giữ RGBA.
2. Cắt đúng y = 700 và căn đầu cùng vị trí.
3. Lưu vào `apps/intro/izumi-vn/assets/sprites/` theo tên ở trên.
4. Ghi prompt đã dùng vào `manifest.json` cùng thư mục.
