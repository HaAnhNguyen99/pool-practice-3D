# pool_cv: đo thế bi từ video thi đấu

Python thuần, không cần numpy/opencv; chỉ cần `ffmpeg`/`ffprobe`.

## Quy trình cho một clip mới

1. **Tìm cú đánh.** Dùng `ffmpeg ... select='gt(scene,0.3)',showinfo` để lấy các mốc chuyển cảnh. Sau đó dựng contact sheet 1 fps có timestamp. Với mỗi cú, cần một khung **camera trên cao** chụp sau khi bi lần trước đã dừng và trước khi cơ thủ đánh. Các đoạn replay nằm giữa hai lần logo chuyển cảnh, không tính là cú mới.
2. **Kiểm tra camera.** Xuất một khung trên cao sạch, không có người che băng, ra PPM (`-pix_fmt rgb24 -c:v ppm`), rồi chạy `python calibrate.py f.ppm --ref ../../calib/<event>.json`. Lệnh này in ra 5 đường thẳng mới cạnh giá trị tham chiếu. Lệch không quá ~2 px thì dùng lại camera cũ. Lệch nhiều hơn thì chạy `python calibrate.py f.ppm ../../calib/<new>.json` để khớp lại. Các vùng quét trong `calibrate.py` và `edges.py` được chỉnh cho khung hình US Open 2023; với khung hình khác cần sửa hằng số ở đầu file.
3. **Đo bi.** Chạy `balls.py f.ppm calib/<event>.json`. Tâm bi bằng tia camera qua tâm đường tròn, giao với mặt phẳng z=−1.125. Nếu bi cái bị tay hoặc cơ che, đặt điểm khởi đầu bằng tay rồi gọi `balls.refine`.
4. **Tính góc.** `geom.theta(cb, ob, pocket)` là bản chuyển nguyên văn `geom()` của `index.html`. Lấy lỗ theo chỗ bi thực sự rơi trong video. Bi sát băng (đo được < 1.125) thì đặt bằng 1.125.
5. **Cắt clip.** Re-encode 720p (`-crf 22 -movflags +faststart`, giữ tiếng), poster là khung trên cao trước cú đánh. Ghi vào `clips/clips.js`.

## Hệ toạ độ

Đơn vị inch, bàn 9 ft là 100×50. x=0 là băng gần camera, y=0 là băng trái trong ảnh. Cùng hệ với `index.html`, nên lỗ 0=(0,0), 3=(0,50) là hai lỗ góc gần camera.

## Bẫy đã gặp

- Mép sáng ở mép dưới ảnh (y≈879) là mép ngoài mặt trên đệm gần, **không** phải x=0.
- Cụm chấm trắng trên nỉ không có tâm ở head spot. Head spot là chấm ở px (960.3, 738.8).
- Nửa dưới bi trắng gần màu nỉ, nên bi cái bắt buộc phải qua bước khớp bán kính cố định.
