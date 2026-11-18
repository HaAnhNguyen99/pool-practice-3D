# Chịu bi lát

> Luyện ngắm bida lỗ trên trình duyệt: mô phỏng 3D góc cắt, bi ảo, độ chồng lấn, quiz đoán góc và thư viện clip cơ thủ chuyên nghiệp khớp theo từng thế bi.

Web luyện ngắm bida lỗ (pool) với mô phỏng 3D, chạy trực tiếp trên trình duyệt (Three.js).

## Tính năng
- **Bàn 3D**: Rasson Mr Sung Acura (xám / đen), Rasson Victory II, chuẩn WPA, bàn quán, hoặc tuỳ chỉnh kích thước lỗ. Có chế độ bàn "đã qua sử dụng" hoặc "mới tinh", đổi được màu nỉ và kích thước 7/8/9 ft.
- **Hình học ngắm**: bi ảo (ghost ball), điểm tiếp xúc, góc cắt θ, độ chồng lấn (`1 − sin θ`), độ lệch tâm ngắm.
- **Khung góc cắt**: hình minh hoạ chồng lấn 2 bi theo góc nhìn ngắm, kèm sơ đồ nhìn từ trên.
- **Sau va chạm**: đường bi cái khi stun (90°) và khi follow (lăn tự nhiên).
- **Độ khó**: sai số cho phép tính theo độ mở lỗ và khoảng cách.
- **Báo lỗi phi vật lý**: báo khi góc cắt > 90°, và cảnh báo khi góc > 85° (quá mỏng, thực tế gần như không thể vào).
- **3 góc camera**: trên cao, 3D tự do, góc nhìn người chơi. Có thêm khung nhỏ hiện góc nhìn người chơi.
- **Quiz**: đoán góc cắt hoặc độ chồng lấn. Có thống kê sai số theo dải góc và xu hướng cắt dày / cắt mỏng.
- **Clip cơ thủ chuyên nghiệp theo góc cắt**: nhúng đoạn YouTube (có thời điểm bắt đầu và kết thúc) cho từng thế bi.
  - Góc của clip được đo từ thế bi dựng lại trên bàn 3D, nên khớp với cú đánh thật.
  - App tự hiện các clip có góc lệch không quá ±7.5° so với thế bi đang xem.
  - Có nút "Dựng thế bi" để đặt lại bi giống trong clip.
  - Có thể xuất / nhập file JSON để chia sẻ thư viện clip. Muốn đưa clip vào sẵn trong app thì thêm vào mảng `SEED_CLIPS` trong `index.html`.

## Chạy
Three.js r160 đã được đặt sẵn trong `vendor/three/` (giấy phép MIT), không cần CDN. Vì trang dùng ES module nên phải mở qua một web server, không mở trực tiếp bằng `file://`:

```bash
python -m http.server 8000
# mở http://localhost:8000
```

## Publish
Đây là trang tĩnh: chỉ cần đưa `index.html`, `index-2d.html` và thư mục `vendor/` lên bất kỳ host tĩnh nào (GitHub Pages, Netlify, Cloudflare Pages…).

- Thư mục `clips/` (clip cắt từ video thi đấu) bị gitignore và **không** được publish. Trên bản online, danh sách clip local sẽ trống; clip YouTube vẫn hoạt động.
- Video và ảnh thumbnail YouTube vẫn được tải từ YouTube.

`index-2d.html` là bản mô phỏng 2D ban đầu.

## Ghi chú
- Số đo miệng lỗ của bàn Acura là ước tính vì chưa có thông số công bố. Bạn có thể chỉnh lại trong menu bàn → Tuỳ chỉnh.
- Logo trên bàn chỉ là chữ mô phỏng, không phải file logo chính thức.
