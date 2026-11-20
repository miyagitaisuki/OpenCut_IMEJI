# Cài OpenCut IMEJI trên Windows

Tóm tắt từ lần cài thật trên Windows 11. Chạy lệnh trong PowerShell, trừ chỗ ghi "bash".

## 1. Công cụ cần cài

| Công cụ | Cách cài | Ghi chú |
|---|---|---|
| Visual Studio 2022 Build Tools | Chọn "Desktop development with C++" | Trình biên dịch cho Rust |
| LLVM | `winget install LLVM.LLVM` | `ffmpeg-sys-next` cần libclang |
| Rust 1.97 | `rustup-init.exe`, rồi `rustup default 1.97.0` | Đừng cài Rust bằng proto (bị lỗi) |
| proto | https://moonrepo.dev/proto | Cài moon 2.3.3 và Bun 1.3.11: `proto install` trong thư mục repo |
| Python 3 | python.org | Cần cho `scripts/*.py`, `slice_sheet.py` (`pip install pillow numpy scipy`) |
| AivisSpeech | aivis-project.com | Giọng đọc intro, cổng 10101 |

Biến môi trường (đặt một lần):

```powershell
setx LIBCLANG_PATH "C:\Program Files\LLVM\bin"
```

`PATH` cần có `%USERPROFILE%\.proto\shims` và `%USERPROFILE%\.cargo\bin`.

## 2. FFmpeg (có H.264)

```powershell
moon run media:setup
```

Lệnh tải FFmpeg dựng sẵn và nhị phân OpenH264 của Cisco. Tắt/bật H.264: `opencut h264 off|on`.

## 3. Dựng CLI

```powershell
cargo build --release -p opencut-cli
```

`cargo test` không dựng lại `target\...\opencut.exe`; sửa code xong phải `cargo build` lại.

## 4. Intro / outro

```powershell
cd apps\intro
bun install
bun run speak scenes\n4-teshimau.json
bun run render scenes\n4-teshimau.props.json
```

Sửa `avatar.json` thì phải chạy lại `speak` trước `render`. Khi sửa file JSON, đừng dùng `Set-Content -Encoding utf8` (thêm BOM làm lỗi đọc file).

## 5. Bài giảng từ textts

```powershell
opencut import-textts bai.mp3 --script bai.txt -o bai.project.json
opencut mascot bai.project.json --avatar apps\intro\public\avatars\chibi
opencut render bai.project.json --burn-subtitles
```

Hoặc trọn chuỗi QBank → textts → OpenCut: `python scripts\opencut_ptc.py lesson --question <id> --mascot apps\intro\public\avatars\chibi --render`
(cần textts REST chạy ở cổng 8000; `python scripts\opencut_ptc.py check` để kiểm).
