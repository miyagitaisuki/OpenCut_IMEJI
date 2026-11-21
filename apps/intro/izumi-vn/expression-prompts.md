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
| `O01_E09_G01.png` | thinking, eyes looking up, lips slightly pressed |
| `O01_E10_G01.png` | winking, one eye closed, the other open, small smile |

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
