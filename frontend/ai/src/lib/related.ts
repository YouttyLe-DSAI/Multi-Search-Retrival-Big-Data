export async function openAtKeyframe(imgUrl: string, imgId?: number) {
  const backend = process.env.NEXT_PUBLIC_BACKEND || 'http://localhost:5000';

  // Lấy pathname '/keyframe/Lxx_Vxxx/NNN.jpg' từ URL tuyệt đối
  let imgpath = imgUrl;
  try {
    const u = new URL(imgUrl);
    imgpath = u.pathname; // nếu imgUrl là full URL thì lấy phần /keyframe/...
  } catch {
    // nếu đã là pathname thì giữ nguyên
  }

  const url = new URL(`${backend}/relatedimg`);
  url.searchParams.set('imgpath', imgpath);
  if (typeof imgId === 'number') url.searchParams.set('imgid', String(imgId));

  const res = await fetch(url.toString());
  if (!res.ok) throw new Error(`relatedimg ${res.status}`);
  const data = await res.json();

  // Mở đúng URL đã kèm t= do backend trả về
  const target = data.video_url_seek || data.video_url;
  if (target) window.open(target, '_blank', 'noopener');

  // Debug (mở DevTools Network/Console nếu cần đối chiếu)
  console.debug('[relatedimg]', {
    imgUrl,
    imgId,
    imgpathSent: imgpath,
    start_sec: data.start_sec,
    keyframe_sec: data.keyframe_sec,
    video_url_seek: data.video_url_seek,
    debug: data.debug,
  });
}
