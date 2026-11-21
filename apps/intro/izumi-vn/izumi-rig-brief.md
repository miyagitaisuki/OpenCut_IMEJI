# Brief: Rig vector nhân vật Izumi (Live2D)

## 1. Mục tiêu
Từ ảnh reference, tạo bộ file vector rig cho nhân vật Izumi (chibi, nhìn thẳng) để dùng trong Live2D Cubism. Bàn giao gồm PSD có layer và file Cubism `.cmo3` / `.can3`.

## 2. Đầu vào
- Ảnh reference chính cho từng nhóm (tóc, mặt, mắt, miệng, thân, tay). Nền xanh `#00A84A` hoặc trong suốt.
- Tất cả cùng phong cách **flat vector**: không gradient, không highlight bán trong suốt, không họa tiết hạt.
- Kích thước tối thiểu **2000 px** cho mỗi bộ phận lớn (tóc, mặt, thân).
- Mỗi bộ phận một file PNG riêng, đặt tên theo mục 4.

## 3. Quy tắc vẽ (bắt buộc)
- Viền nâu đậm `#4A2A1F`, độ dày đều giữa các bộ phận.
- Màu phẳng. Bóng chỉ là một mảng màu tối hơn, cùng tông.
- Bảng màu cố định: da, tóc nâu, navy đồng phục, trắng, đỏ nơ, đen giày. Ghi mã màu vào file thiết kế.
- Nhìn thẳng. Hai bên đối xứng: cặp trái và phải là hai file riêng, không lật ảnh sau khi vẽ.
- Mỗi bộ phận vẽ trong cùng khung **2400 × 2800 px** và đặt đúng vị trí so với mặt (mục 5).

## 4. Danh sách bộ phận (tên file = tên ArtMesh)
Quy ước trái/phải theo **nhân vật** (bên trái nhân vật nằm ở bên phải ảnh).

| Nhóm | File |
|---|---|
| Tóc | `HairBack`, `HairFront`, `HairSideL`, `HairSideR`, `HairTailL`, `HairTailR` |
| Mặt | `Face`, `Neck` |
| Mắt | `WhiteL`, `WhiteR`, `IrisL`, `IrisR`, `EyeClosedL`, `EyeClosedR`, `EyelashL_Upper`, `EyelashR_Upper` |
| Lông mày | `BrowL`, `BrowR` |
| Mũi, miệng | `Nose`, `Mouth_LipUpper`, `Mouth_LipLower`, `Mouth_Inside` |
| Thân, tay | `Body_Skirt`, `ArmL`, `ArmR`, `HandL`, `HandR`, `Book` |

Tổng 31 file. Mắt tách riêng tròng đen và lòng trắng; mắt nhắm là một file riêng.

## 5. Canvas và vị trí
- Canvas **2400 × 2800 px**, gốc (0, 0) ở góc trên trái.
- Mặt căn giữa tại **(1200, 1050)**, chiều rộng mặt khoảng **900 px**.
- Hai mắt nằm ngang nhau, cách tâm mặt khoảng ±200 px, cùng độ cao. Mũi và miệng nằm dưới mắt theo tỉ lệ chibi.
- Tóc, thân, tay đặt theo cùng hệ tọa độ. Khi nhập vào Cubism không cần căn lại.

## 6. Thứ tự lớp (dưới → trên)
1. `HairBack`
2. `Body_Skirt`
3. `ArmL`, `ArmR`
4. `HandL`, `HandR`
5. `Neck`
6. `Face`
7. `Nose`
8. `Mouth_Inside`
9. `Mouth_LipLower`
10. `Mouth_LipUpper`
11. `WhiteL`, `IrisL`, `WhiteR`, `IrisR`
12. `EyeClosedL`, `EyeClosedR` (mặc định ẩn)
13. `BrowL`, `BrowR`
14. `HairTailL`, `HairTailR`
15. `HairSideL`, `HairSideR`
16. `HairFront`

## 7. Bàn giao
- **PSD**: 8-bit RGB, mỗi bộ phận một layer có tên đúng, không gộp layer.
- **PNG** tách riêng từng bộ phận, nền trong suốt, cùng kích thước canvas.
- **Ghi chú**: bảng màu và danh sách file đã dùng.
- **Cubism**: `.cmo3` / `.can3` đã có mesh, deformer, tham số; xuất `.model3.json`.

## 8. Kiểm tra trước khi giao
- [ ] Đủ 31 file, đúng tên, không trùng.
- [ ] Không có gradient, highlight, hạt.
- [ ] Viền đều, cùng độ dày.
- [ ] Cặp trái/phải là hai file riêng, hình khớp nhau.
- [ ] Mắt, lông mày, mũi, miệng cùng tâm với mặt khi xếp chồng.
- [ ] Mở PSD thấy đúng thứ tự lớp.

## 9. Việc của người làm rig (Cubism Editor)
Tạo mesh, deformer và tham số:
- `ParamAngleX`, `ParamAngleY`, `ParamAngleZ` (nghiêng đầu)
- `ParamEyeLOpen`, `ParamEyeROpen` (chớp mắt)
- `ParamMouthOpenY`, `ParamMouthForm` (miệng theo nguyên âm)
- Tham số tóc, tay (đung đưa)

Sau đó xuất `.model3.json` và các file đi kèm.
