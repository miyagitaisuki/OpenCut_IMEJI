# Brief: tách sprite thành base trống mặt + lớp biểu cảm (Izumi, visual novel video)

## 1. Mục tiêu
Mỗi nhân vật có **một base** (đầu, tóc, cổ, thân, tay, trang phục, mặt trống) và **các lớp biểu cảm** (mắt, lông mày, miệng) đặt chồng lên đúng vị trí trên mặt. Đổi biểu cảm không cần sinh lại cả nhân vật. Đổi trang phục chỉ thay lớp `outfit`.

## 2. Cấu trúc lớp (dưới → trên)
1. `base_body` — thân, tay, cổ, váy/áo (không có mặt).
2. `base_hair_back` — tóc sau.
3. `base_face` — khuôn mặt trống (da, má hồng, tai), không có mắt/lông mày/miệng/mũi.
4. `expr_brow_L`, `expr_brow_R` — lông mày.
5. `expr_eye_L`, `expr_eye_R` — mắt (mở, nhắm, hoặc nhắm một bên).
6. `expr_mouth` — miệng (đóng, cười, mở, tròn...).
7. `base_hair_front` — tóc mái và tóc mai (phủ lên một phần lông mày và mắt khi cần).

Thứ tự trên là chuẩn. Tóc mái luôn nằm trên lông mày, nên lông mày bị che đúng cách.

## 3. Khóa vị trí (quan trọng nhất)
- Mọi lớp sinh ra trên **cùng canvas và cùng kích thước** với base.
- Base là gốc tọa độ. Sau khi có base đã duyệt, **đo tọa độ mắt, lông mày, miệng** trên base (tâm và kích thước). Ghi vào `slots.json`.
- Lớp biểu cảm phải căn đúng vào slot. Không tự căn bằng mắt.
- Đường cắt waist: y = 700 (theo bản chuẩn 1024 px), giữ như các sprite trước.

## 4. Sinh base trống mặt
Đính kèm `7.png` làm anchor (identity). Prompt:
```
Same chibi anime girl as the reference: same brown wavy hair, same head size, same outfit, same proportions.
Upper body, cropped at the waist. The face is completely blank: no eyes, no eyebrows, no mouth, no nose. Smooth skin, soft pink cheeks only.
Hands at sides. Flat clean anime style, thin dark-brown outline, plain solid white background #FFFFFF, no shadow, no gradient.
Negative: eyes, eyelashes, eyebrows, mouth, nose, lips, teeth, face features, text, watermark, legs.
```
Kiểm tra: mặt không có chi tiết nào. Nếu AI vẫn vẽ mắt, thử lại hoặc dùng face-inpaint trên ảnh đã có để xóa mắt và miệng.

## 5. Sinh lớp biểu cảm
Mỗi biểu cảm gồm **ba file nhỏ**, nền trong suốt hoặc trắng, cùng kích thước khung với base (không cắt riêng):

| Mã | Biểu cảm | Mắt | Lông mày | Miệng |
|---|---|---|---|---|
| E01 | neutral | mở | thường | khép |
| E02 | smile | nhắm cười (vòng cung) | thường | ω |
| E03 | happy | mở sáng | nhấc nhẹ | mở cười |
| E04 | angry | mở, mí nặng | nhíu vào trong | mím |
| E05 | sad | mở, mí cụp | cụp vào trong | hơi cong xuống |
| E06 | shy | mở, nhìn lệch | nhấc nhẹ | nhỏ, nghiêng |
| E07 | surprised | mở to | nhấc cao | tròn mở |
| E08 | worried | mở | nhíu nhẹ | méo nhẹ |
| E09 | thinking | nhìn lên | thường | mím nhẹ |
| E10 | wink | một mắt nhắm | thường | cười nhẹ |

Mỗi biểu cảm **sinh riêng từng lớp** bằng prompt "only the {bộ phận}, on solid white, centered in the slot". Ví dụ:
```
Only the mouth of a chibi anime girl, open happy smile, small, flat clean anime style, thin dark-brown outline, solid white background #FFFFFF, centered, no face, no skin.
```

## 6. Tách nền và chuẩn hóa lớp
- Lớp biểu cảm nền trắng: loang từ mép ảnh (không dùng ngưỡng màu, vì môi và răng có màu sáng).
- Lưu RGBA. Crop theo slot, không crop theo nội dung. Giữ offset (left, top) để ghép đúng vị trí.
- Đặt tên: `E{nn}_{brow|eye|mouth}_{L|R}.png`, ví dụ `E04_brow_L.png`.

## 7. Bảng slot (`slots.json`)
```json
{
  "canvas": [1024, 1024],
  "waist_y": 700,
  "eye_L":   {"cx": 0, "cy": 0, "w": 0, "h": 0},
  "eye_R":   {"cx": 0, "cy": 0, "w": 0, "h": 0},
  "brow_L":  {"cx": 0, "cy": 0, "w": 0, "h": 0},
  "brow_R":  {"cx": 0, "cy": 0, "w": 0, "h": 0},
  "mouth":   {"cx": 0, "cy": 0, "w": 0, "h": 0}
}
```
Điền số đo từ base đã duyệt (bước 3). Không điền số đoán.

## 8. Kiểm tra
- [ ] Base không có chi tiết mặt nào.
- [ ] Lớp mắt, lông mày, miệng đúng slot khi chồng lên base.
- [ ] Tóc mái che đúng lông mày ở các biểu cảm buồn hoặc giận.
- [ ] Viền và màu của lớp biểu cảm khớp với base (cùng dày, cùng nâu).
- [ ] Miệng đóng và miệng mở đều căn đúng vị trí cằm.

## 9. Ghép trong Remotion
Composition đọc `base` + `expr_*` theo mã biểu cảm trong kịch bản. Mỗi dòng thoại có trường `expression` (ví dụ `E04`). Lip-sync: đổi lớp `expr_mouth` theo nguyên âm (あいうえおん).

## 10. Phạm vi và giới hạn
- Không đảm bảo lớp biểu cảm khớp hoàn hảo lần đầu. Cần chỉnh slot và loại ảnh lệch.
- Biểu cảm mạnh (giận, ngạc nhiên) đôi khi cần vẽ lại lông mày riêng.
- Bản quyền: chỉ dùng ảnh do bạn tạo hoặc có quyền dùng.
