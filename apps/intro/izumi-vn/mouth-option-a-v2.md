# Phương án A (v2): Miệng có tham số, vẽ thành một hình

Thay đổi so với v1: miệng được vẽ **một lần** (môi và phần trong cùng một hình), rồi tách thành ba layer. Cách này tránh lỗi chồng lớp đã gặp ở v8: môi trên che răng, môi dưới tạo viền thứ hai.

## 1. Tham số và hình cần đạt

| Mora | `ParamMouthOpenY` | `ParamMouthForm` | Hình miệng |
|---|---|---|---|
| あ (a) | 1.00 | 0.30 | Mở to, thấy răng trên và lưỡi |
| い (i) | 0.30 | 1.00 | Mở hẹp, kéo ngang |
| う (u) | 0.35 | -1.00 | Tròn nhỏ, chu môi |
| え (e) | 0.55 | 0.70 | Mở vừa, khóe kéo nhẹ |
| お (o) | 0.75 | -0.70 | Tròn, mở vừa-to |
| ん, っ, pause, ま ば ぱ | 0.00 | 0.00 | Đóng, đường ω |

Thang: `ParamMouthOpenY` 0 → 1, `ParamMouthForm` -1 → 1. Đặt keyform tại các điểm trên, nội suy tuyến tính giữa chúng.

## 2. Kích thước

- Rộng miệng khoảng **0.14–0.25 chiều rộng mặt** (mặt ≈ 991 px trong PSD v7–v8, nên miệng ≈ 140–250 px).
- Lưu ý: bản v1 ghi "tối thiểu 300 px" là sai với canvas 2400 px. Bỏ con số này.
- Miệng mở hiện tại (`Mouth_Inside`) rộng 172 px, nằm trong khoảng.

## 3. Layer và thứ tự

Dưới → trên: `Mouth_Inside` → `Mouth_LipLower` → `Mouth_LipUpper`.

- `Mouth_Inside`: phần trong miệng (răng trên, lưỡi). Viền ngoài của nó nằm **dưới** môi, bị môi che.
- `Mouth_LipUpper`, `Mouth_LipLower`: môi, có mép trong cắt đúng theo lỗ miệng.
- Khi miệng mở, mép trong của môi trên và môi dưới phải trùng với mép trên và dưới của `Mouth_Inside`. Không có khoảng trống, không có viền thứ hai.

## 4. Quy tắc tránh chồng lớp (bắt buộc)

1. Vẽ cả ba phần trong **một file** (một hình), sau đó tách thành layer. Không vẽ môi và phần trong riêng.
2. Đường viền ngoài của miệng (`#4A2A1F`) chỉ xuất hiện ở mép môi. Không có viền thừa trên phần trong.
3. Răng trắng nằm **trong** lỗ miệng, không bị môi trên che quá 10% chiều cao.
4. Môi dưới không tạo đường cong thứ hai dưới phần trong. Đáy miệng là một đường duy nhất.
5. Kiểm tra: phóng to 300%, không có đường viền kép, không có khe sáng giữa môi và phần trong.

## 5. Prompt tạo art

### Prompt 1: miệng mở một hình (dùng để tách thành ba layer)
```
Flat vector anime chibi mouth, one single image, for a Live2D rig. Open mouth saying "a" (あ), facing front.
Include the lips and the mouth opening together as one shape: upper lip, lower lip, upper teeth, tongue, and mouth interior.
The lip outline is the outer edge only. Inside the opening there are no extra outlines. The upper teeth are inside the opening, not covered by the upper lip.
Style: solid color fills only, no gradients, no highlights, no textures, no grain.
Uniform dark brown outline #4A2A1F, same line weight as a clean flat vector icon.
Colors: lips #F2B8A6 with a flat darker lower lip #E8A090, mouth interior #7D3B38, tongue #E67E7E, teeth #FFFFFF with a thin #4A2A1F separation line.
One closed outline around the whole mouth. Mouth fills about 60% of a 1000×600 px area, centered, on a solid green #00A84A background.
```

### Prompt 2: miệng đóng ω (trạng thái nghỉ)
```
Flat vector anime chibi mouth, closed smile shaped like the Japanese letter ω, for a Live2D rig.
Solid fills only, uniform #4A2A1F outline, lips #F2B8A6, no gradient, no highlight.
Centered on a solid green #00A84A background, same scale as the open mouth in the previous prompt (lip width about 60% of the open mouth's width).
```

### Prompt 3: hình tham chiếu cho keyform i, u, o (chỉ để kiểm tra)
```
Three flat vector anime chibi mouths in a row, same style and size, for a Live2D rig:
1) "i" (い): wide flat smile, slight opening, corners pulled sideways.
2) "u" (う): small round pout, lips pushed forward.
3) "o" (お): round open mouth, medium size.
Each is one closed outline, solid fills only, uniform #4A2A1F outline, no gradient, same interior color #7D3B38, on solid green #00A84A.
```

Gửi kèm `Face.png` và ảnh miệng hiện tại làm tham chiếu khi chạy prompt.

## 6. Cách tách và đặt vào PSD

1. Tách ảnh miệng mở thành ba PNG: `Mouth_Inside`, `Mouth_LipLower`, `Mouth_LipUpper`, cùng canvas và cùng tâm.
2. Kiểm tra mép trên và mép dưới khớp với viền trong của môi. Nếu không khớp, chỉnh mép phần trong cho khớp với môi, không chỉnh ngược lại.
3. Đặt vào PSD đúng thứ tự lớp ở mục 3.

## 7. Bàn giao Cubism

1. Gắn `Mouth_LipUpper` và `Mouth_LipLower` vào deformer, điều khiển bởi `ParamMouthOpenY` và `ParamMouthForm`.
2. Gắn `Mouth_Inside` vào `ParamMouthOpenY`, ẩn hoặc đặt opacity 0 khi `ParamMouthOpenY = 0`.
3. Tạo keyform theo bảng mục 1.
4. Kiểm tra từng mora trong viewer.

## 8. Nghiệm thu

- [ ] Phóng to 300%: không có đường viền kép, không có khe sáng.
- [ ] Răng trắng nằm trong lỗ miệng, không bị che quá 10%.
- [ ] Ở `ParamMouthOpenY = 0`, không thấy phần trong miệng.
- [ ] Miệng đối xứng ở `ParamMouthForm` = ±1, trừ hình u, o.
- [ ] Đoạn audio mẫu: miệng đổi đúng nhịp âm tiết.

## 9. Bàn giao

- `.cmo3` / `.can3` có `ParamMouthOpenY` và `ParamMouthForm`.
- `.model3.json` vào `public/avatars/izumi/`.
- Ghi chú: danh sách layer miệng đã vẽ lại.
