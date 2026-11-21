# Thiết lập trong Live2D Cubism Editor: Izumi

File nguồn: `izumi-rig-final.psd` (2400×2800, 31 layer, tên đã sạch, thứ tự đúng brief).

## 1. Lỗi đã biết trong file (cần biết trước khi rig)
- **Hạt tối sau cằm** trong `HairBack` vẫn còn. Không ảnh hưởng rig, nhưng sẽ hiện trên khung hình.
- **Khe sáng trên trán bên trái** (`Face` lộ qua `HairFront`) vẫn còn.
- **`Nose` chỉ 16 px**, gần như không nhìn thấy. Cân nhắc xóa hoặc vẽ lại.
- **Lông mi trên** (`EyelashL_Upper`, `EyelashR_Upper`) có khối đặc.
- Vị trí các layer là ước lượng, cần kiểm tra khi đặt mesh.

## 2. Import PSD vào Cubism
1. Mở Cubism Editor, tạo project mới.
2. Import file `izumi-rig-final.psd`. Chọn import theo layer, mỗi layer thành một ArtMesh.
3. Giữ tên ArtMesh đúng như tên layer (không đổi tên).
4. Kiểm tra thứ tự vẽ trong Parts giống mục 4 dưới đây.

## 3. Nhóm Parts
| Part | ArtMesh |
|---|---|
| Hair | `HairBack`, `HairTailL`, `HairTailR`, `HairSideL`, `HairSideR`, `HairFront` |
| Body | `Body_Skirt`, `Tie`, `Book` |
| Arms | `ArmL`, `ArmR`, `HandL`, `HandR` |
| Face | `Neck`, `Face`, `Nose`, `BrowL`, `BrowR` |
| Eyes | `WhiteL`, `IrisL`, `EyeHighlightL`, `WhiteR`, `IrisR`, `EyeHighlightR`, `EyelashL_Upper`, `EyelashR_Upper`, `EyeClosedL`, `EyeClosedR` |
| Mouth | `Mouth_Inside`, `Mouth_LipLower`, `Mouth_LipUpper` |

## 4. Thứ tự vẽ (dưới → trên)
`HairBack` → `Body_Skirt` → `Tie` → `ArmL` → `ArmR` → `Book` → `HandL` → `HandR` → `Neck` → `Face` → `Nose` → `Mouth_Inside` → `Mouth_LipLower` → `Mouth_LipUpper` → `WhiteL` → `IrisL` → `EyeHighlightL` → `WhiteR` → `IrisR` → `EyeHighlightR` → `EyelashL_Upper` → `EyelashR_Upper` → `EyeClosedL` → `EyeClosedR` → `BrowL` → `BrowR` → `HairTailL` → `HairTailR` → `HairSideL` → `HairSideR` → `HairFront`

## 5. Tham số cần tạo
| Tham số | Phạm vi | Dùng cho |
|---|---|---|
| `ParamAngleX`, `ParamAngleY`, `ParamAngleZ` | -30 … 30 | Nghiêng đầu, xoay đầu |
| `ParamEyeLOpen`, `ParamEyeROpen` | 0 … 1 | Mở/nhắm mắt (chớp) |
| `ParamEyeLSmile`, `ParamEyeRSmile` | 0 … 1 | Cười mắt |
| `ParamMouthOpenY` | 0 … 1 | Độ mở miệng |
| `ParamMouthForm` | -1 … 1 | Hình dạng miệng |
| `ParamBodyAngleX`, `ParamBodyAngleZ` | -10 … 10 | Nghiêng thân |
| `ParamBreath` | 0 … 1 | Thở |
| `ParamCheek` | 0 … 1 | Má hồng |

## 6. Keyform miệng (phương án A)
| Mora | `ParamMouthOpenY` | `ParamMouthForm` |
|---|---|---|
| あ | 1.00 | 0.30 |
| い | 0.30 | 1.00 |
| う | 0.35 | -1.00 |
| え | 0.55 | 0.70 |
| お | 0.75 | -0.70 |
| ん, っ, đóng | 0.00 | 0.00 |

- Tại `ParamMouthOpenY = 0`: ẩn `Mouth_Inside`.
- Môi trên và môi dưới deform theo cả hai tham số.
- Với `ParamMouthOpenY = 0` và `ParamMouthForm = 0`, miệng là đường đóng.

## 7. Mắt chớp
- `EyeClosedL/R` ẩn mặc định. Khi `ParamEyeLOpen = 0` (hoặc `ParamEyeROpen = 0`), hiện lớp mắt nhắm và ẩn mắt mở tương ứng.
- Mắt mở (`WhiteL`, `IrisL`...) keyform: 1 → mở, 0 → ẩn.

## 8. Kiểm tra trước khi xuất
- [ ] Đủ 31 ArtMesh, không trùng tên.
- [ ] Miệng: đủ 6 hình keyform, không chồng viền.
- [ ] Chớp mắt: mắt mở ↔ mắt nhắm không lộ khoảng trống.
- [ ] Xoay đầu ±30: tóc, mặt, cổ không tách rời.
- [ ] Xem ở chế độ Preview, không có mesh lạ.

## 9. Xuất
1. Lưu project `.cmo3`.
2. Export `.moc3`, `.model3.json`, texture (`.png`) và `.physics3.json` nếu có.
3. Đặt vào `apps/intro/public/avatars/izumi/`.
4. Báo lại để mình kiểm tra tên tham số khớp với `Live2dAvatar.tsx`.

## 10. Ghi chú
- File `.cmo3` phải tạo bằng Cubism Editor trên máy bạn. Môi trường của mình không có Cubism nên không tạo được.
- Nếu bạn muốn tạo mesh tự động, Cubism có tính năng Auto Mesh. Vẫn cần kiểm tra thủ công.
