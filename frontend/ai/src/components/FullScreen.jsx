import Image from "next/image";
import { useEffect, useMemo, useState } from "react";
import { AiFillPicture, AiFillPlayCircle, AiFillVideoCamera } from "react-icons/ai";
import ImageListRelated from "./ImageListRelated";

function fmtSec(s) {
  if (s === undefined || s === null || s === "") return null;
  const n = Number(s);
  if (Number.isNaN(n)) return null;
  return (Math.round(n * 1000) / 1000).toString();
}

// Helper to get YouTube URL at specific time
function getYouTubeUrlAtTime(url, sec) {
  if (!url) return "";
  try {
    const urlObj = new URL(url);
    let videoId = "";
    if (urlObj.hostname === "youtu.be") {
      videoId = urlObj.pathname.slice(1);
    } else if (urlObj.hostname.includes("youtube.com")) {
      videoId = urlObj.searchParams.get("v");
    }
    if (videoId) {
      return `https://www.youtube.com/watch?v=${videoId}&t=${Math.floor(sec)}s`;
    }
  } catch {}
  return url;
}

export default function FullScreen({ fullScreenImg, setFullScreenImg, relatedObj = {} }) {
  const [showPlayer, setShowPlayer] = useState(false);
  const [imageError, setImageError] = useState(false);
  const [viewMode, setViewMode] = useState('image'); // 'image' hoặc 'video'
  const [playerError, setPlayerError] = useState(false);
  const [selectedKeyframe, setSelectedKeyframe] = useState(null);
  const [currentVideoTime, setCurrentVideoTime] = useState(null);
  const [fpsList, setFpsList] = useState({});
  const [liveTime, setLiveTime] = useState(null);
  const [liveFrame, setLiveFrame] = useState(null);

  // Load fps data
  useEffect(() => {
    const loadFpsData = async () => {
      try {
        const response = await fetch('/fps.json');
        const data = await response.json();
        setFpsList(data);
      } catch (error) {
        console.error('Failed to load fps data:', error);
      }
    };
    loadFpsData();
  }, []);

  // Khai báo tất cả biến trước khi sử dụng trong hooks
  const secStr =
    relatedObj && relatedObj.keyframe_sec !== undefined ? fmtSec(relatedObj.keyframe_sec) : null;
  const frameStr =
    relatedObj && relatedObj.frame_idx !== undefined ? String(relatedObj.frame_idx) : null;

  // Lấy video ID và FPS để tính frame index
  const videoId = relatedObj?.video_id || fullScreenImg?.video_id;
  const fps = videoId ? (fpsList[videoId] || 25.0) : 25.0;

  const rawUrl = relatedObj?.video_url || "";
  const youtubeUrl = relatedObj?.youtube_url || rawUrl;  // Ưu tiên youtube_url từ backend
  
  // Kiểm tra xem có video local không (không phải YouTube)
  const hasLocalVideo = rawUrl && rawUrl.startsWith('http://localhost:5001/video/');
  
  const startSec = useMemo(() => {
    if (secStr) return Number(secStr);
    if (relatedObj?.video_range?.[0]) return Number(relatedObj.video_range[0]);
    return 0;
  }, [secStr, relatedObj]);

  // Tính time và frame index hiện tại
  const getDisplayTimeAndFrame = () => {
    if (viewMode === 'video' && currentVideoTime !== null) {
      // Khi đang xem video và có thời điểm pause
      const frameIndex = Math.floor(currentVideoTime * fps);
      return {
        time: currentVideoTime.toFixed(2),
        frame: frameIndex.toString()
      };
    }
    
    // Nếu có keyframe được chọn, hiển thị time của keyframe đó
    if (selectedKeyframe) {
      // Tính toán thời gian của keyframe được chọn
      let keyframeTime = startSec;
      
      if (selectedKeyframe.sec) {
        keyframeTime = selectedKeyframe.sec;
      } else if (relatedObj?.near_keyframes && Array.isArray(relatedObj.near_keyframes)) {
        const index = relatedObj.near_keyframes.findIndex(k => k === selectedKeyframe);
        if (index !== -1) {
          keyframeTime = startSec + (index * 0.5);
        }
      }
      
      const currentTime = keyframeTime.toFixed(2);
      const currentFrame = Math.floor(keyframeTime * fps).toString();
      return { time: currentTime, frame: currentFrame };
    }
    
    // Mặc định hiển thị thông tin của keyframe gốc
    const time = secStr || "0";
    const frame = frameStr || Math.floor((Number(secStr) || 0) * fps).toString();
    return { time, frame };
  };

  const { time: displayTime, frame: displayFrame } = getDisplayTimeAndFrame();

  // URL ưu tiên có seek từ BE
  const seekUrl = relatedObj?.video_url_seek
    ? relatedObj.video_url_seek
    : rawUrl && hasLocalVideo
    ? `${rawUrl}${rawUrl.includes("?") ? "&" : "?"}t=${startSec}s`
    : "";

  const externalUrl = seekUrl || rawUrl;

  const hasVideo = hasLocalVideo;

  // Lấy thời gian từ keyframe được chọn
  // Nếu keyframe chỉ có URL, cần parse để lấy thông tin hoặc sử dụng logic khác
  const getKeyframeTime = (keyframe) => {
    if (!keyframe) return startSec;
    
    // Nếu keyframe có thời gian trực tiếp từ backend (sau khi sửa)
    if (keyframe.sec) {
      return keyframe.sec;
    }
    
    // Fallback: sử dụng index trong near_keyframes
    if (relatedObj?.near_keyframes && Array.isArray(relatedObj.near_keyframes)) {
      const index = relatedObj.near_keyframes.findIndex(k => k === keyframe);
      if (index !== -1) {
        // Giả sử mỗi keyframe cách nhau 0.5 giây
        return startSec + (index * 0.5);
      }
    }
    
    return startSec;
  };

  // Sử dụng thời gian từ keyframe được chọn hoặc keyframe gốc
  const currentStartSec = getKeyframeTime(selectedKeyframe);

  // URL với thời gian mới
  const currentSeekUrl = selectedKeyframe && hasLocalVideo ? 
    (relatedObj?.video_url_seek || `${rawUrl}${rawUrl.includes("?") ? "&" : "?"}t=${currentStartSec}s`) :
    seekUrl;

  const currentExternalUrl = currentSeekUrl || rawUrl;

  // Tạo key duy nhất để force re-render iframe khi thay đổi keyframe
  const iframeKey = `video-${selectedKeyframe?.id || 'original'}-${currentStartSec}`;

  useEffect(() => {
    if (fullScreenImg == null) {
      setShowPlayer(false);
      setImageError(false);
      setViewMode('image');
      setPlayerError(false);
      setSelectedKeyframe(null);
      setCurrentVideoTime(null);
    }
  }, [fullScreenImg]);

  // Tự động chuyển sang video nếu không có ảnh hoặc ảnh lỗi và có local video
  useEffect(() => {
    if (imageError && hasLocalVideo) {
      setViewMode('video');
    }
  }, [imageError, hasLocalVideo]);

  const closeModal = () => setFullScreenImg(null);

  const handlePlayClick = () => {
    // 1) mở tab mới
    if (externalUrl) {
      // dùng noopener/noreferrer để an toàn
      const win = window.open(externalUrl, "_blank", "noopener,noreferrer");
      // nếu bị chặn popup, khuyên người dùng bật popups cho site (tuỳ chọn)
      if (!win) {
        console.warn("Popup bị chặn bởi trình duyệt.");
      }
    }
    // 2) đồng thời phát trong modal
    setViewMode('video');
  };

  const handleImageError = () => {
    setImageError(true);
    // Tự động chuyển sang video nếu có local video
    if (hasLocalVideo) {
      setViewMode('video');
    }
  };

  const handlePlayerError = (error) => {
    console.error("Video player error:", error);
    setPlayerError(true);
  };

  const toggleViewMode = () => {
    setViewMode(viewMode === 'image' ? 'video' : 'image');
    setPlayerError(false); // Reset error khi chuyển mode
    if (viewMode === 'video') {
      setCurrentVideoTime(null); // Reset video time khi chuyển về image
    }
  };

  // Xử lý click vào keyframe khác trong sidebar
  const handleKeyframeClick = (keyframe) => {
    if (keyframe) {
      setSelectedKeyframe(keyframe);
      setViewMode('image'); // Hiển thị ảnh keyframe trước, không tự động chuyển sang video
      setPlayerError(false);
      setImageError(false); // Reset image error để hiển thị ảnh mới
      setCurrentVideoTime(null); // Reset video time
    }
  };

  // Listen for keydown to change frame and play/pause
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (viewMode !== 'video' || !hasLocalVideo) return;
      
      const videoElement = document.querySelector('video');
      if (!videoElement) return;
      
      // Ngăn chặn default behavior cho tất cả các phím điều khiển
      if (e.key === " " || e.code === "Space" || e.key === "," || e.key === ".") {
        e.preventDefault();
        e.stopPropagation();
      }
      
      if (e.key === " " || e.code === "Space") {
        // Space to play/pause
        if (videoElement.paused) {
          videoElement.play();
        } else {
          videoElement.pause();
        }
        return;
      }
      
      const currentTime = videoElement.currentTime;
      const frameTime = 1 / fps;
      
      if (e.key === ",") {
        // Previous frame - sử dụng logic frame-based để đảm bảo chính xác
        const currentFrame = Math.round(currentTime * fps);
        const newFrame = Math.max(0, currentFrame - 1);
        const newTime = newFrame / fps;
        videoElement.currentTime = newTime;
        setCurrentVideoTime(newTime);
        setLiveTime(newTime.toFixed(2));
        setLiveFrame(newFrame.toString());
      } else if (e.key === ".") {
        // Next frame - sử dụng logic frame-based để đảm bảo chính xác
        const currentFrame = Math.round(currentTime * fps);
        const newFrame = currentFrame + 1;
        const newTime = newFrame / fps;
        const maxTime = videoElement.duration || newTime;
        if (newTime <= maxTime) {
          videoElement.currentTime = newTime;
          setCurrentVideoTime(newTime);
          setLiveTime(newTime.toFixed(2));
          setLiveFrame(newFrame.toString());
        }
      }
    };
    
    // Sử dụng document thay vì window và useCapture=true để bắt sự kiện trước
    document.addEventListener("keydown", handleKeyDown, true);
    return () => document.removeEventListener("keydown", handleKeyDown, true);
  }, [viewMode, hasLocalVideo, fps]);

  // Live time/frame update for video
  const handleTimeUpdate = (e) => {
    const t = e.target.currentTime;
    setLiveTime(t.toFixed(2));
    setLiveFrame(Math.round(t * fps).toString());
  };

  if (fullScreenImg == null) return null;
  
  // Nếu không có ảnh hoặc ảnh lỗi, chỉ hiển thị video
  const shouldShowVideo = viewMode === 'video' || imageError || !fullScreenImg?.imgpath;

  return (
    <div
      onClick={closeModal}
      className="fixed inset-0 w-screen h-screen bg-black/90 backdrop-blur-sm flex items-center justify-center z-50 p-4"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="flex gap-8 max-h-[90vh] max-w-[95vw] w-full items-center justify-center"
      >
        {/* Main Content Area */}
        <div className="relative bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900 rounded-2xl shadow-2xl overflow-hidden border border-gray-700 flex-shrink-0">
          {/* Control Bar */}
          <div className="absolute top-4 left-4 z-20 flex gap-3">
            {hasVideo && (
              <button
                onClick={toggleViewMode}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 shadow-lg backdrop-blur-sm ${
                  viewMode === 'image' 
                    ? 'bg-blue-600/90 text-white hover:bg-blue-700/90 shadow-blue-500/25' 
                    : 'bg-gray-800/90 text-white hover:bg-gray-700/90 shadow-gray-500/25'
                }`}
                title={viewMode === 'image' ? 'Chuyển sang video' : 'Chuyển sang ảnh'}
              >
                {viewMode === 'image' ? <AiFillVideoCamera size={18} /> : <AiFillPicture size={18} />}
              </button>
            )}
            {youtubeUrl && (
              <button
                onClick={() => window.open(getYouTubeUrlAtTime(youtubeUrl, currentStartSec), "_blank", "noopener,noreferrer")}
                className="px-4 py-2 rounded-lg text-sm font-medium bg-red-600/90 text-white hover:bg-red-700/90 transition-all duration-200 shadow-lg shadow-red-500/25 backdrop-blur-sm"
                title="Mở YouTube tại thời điểm này"
              >
                YouTube
              </button>
            )}
            {selectedKeyframe && (
              <button
                onClick={() => setSelectedKeyframe(null)}
                className="px-4 py-2 rounded-lg text-sm font-medium bg-green-600/90 text-white hover:bg-green-700/90 transition-all duration-200 shadow-lg shadow-green-500/25 backdrop-blur-sm"
                title="Quay lại keyframe gốc"
              >
                Reset
              </button>
            )}
          </div>

          {/* Close Button */}
          <button
            onClick={closeModal}
            className="absolute top-4 right-4 z-20 w-10 h-10 rounded-full bg-black/50 hover:bg-black/70 text-white flex items-center justify-center transition-all duration-200 backdrop-blur-sm text-2xl"
            title="Đóng"
          >
            ×
          </button>

          {/* Media Container */}
          <div className="relative w-[1000px] h-[562px] rounded-2xl overflow-hidden bg-black/50">
            {!shouldShowVideo ? (
              <>
                <Image
                  src={selectedKeyframe?.imgpath || fullScreenImg.imgpath}
                  fill
                  className="rounded-2xl opacity-100 object-contain"
                  alt=""
                  onError={handleImageError}
                />
              </>
            ) : (
              <div className="absolute inset-0 bg-black rounded-2xl flex items-center justify-center">
                {hasLocalVideo ? (
                  <video
                    key={iframeKey}
                    src={currentStartSec > 0 ? `${rawUrl}#t=${currentStartSec}` : rawUrl}
                    controls
                    className="w-full h-full object-contain rounded-2xl"
                    onError={handlePlayerError}
                    onPause={(e) => {
                      setCurrentVideoTime(e.target.currentTime);
                      // Xóa focus khỏi video element khi pause để tránh bị focus
                      e.target.blur();
                    }}
                    onPlay={() => setCurrentVideoTime(null)}
                    onSeeked={(e) => setCurrentVideoTime(e.target.currentTime)}
                    onLoadedMetadata={(e) => {
                      try {
                        if (currentStartSec > 0 && Math.abs(e.currentTarget.currentTime - currentStartSec) > 0.25) {
                          e.currentTarget.currentTime = currentStartSec;
                        }
                      } catch {}
                    }}
                    onTimeUpdate={handleTimeUpdate}
                  />
                ) : (
                  <div className="w-full h-full flex flex-col items-center justify-center text-white">
                    <button
                      onClick={() => setViewMode('image')}
                      className="group px-8 py-8 bg-gradient-to-br from-gray-700 to-gray-800 hover:from-gray-600 hover:to-gray-700 rounded-full transition-all duration-300 shadow-2xl hover:shadow-gray-500/25 transform hover:scale-105"
                      title="Không có video, quay lại xem ảnh"
                    >
                      <AiFillPlayCircle size={64} className="text-white group-hover:text-gray-200" />
                    </button>
                    <div className="mt-6 text-gray-400 text-lg font-medium">Không có video để phát</div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Info Section - Moved outside video container */}
          <div className="p-6 bg-gradient-to-r from-gray-800/50 to-gray-700/50 border-t border-gray-600/50">
            {/* Time & Frame Info */}
            {viewMode === 'video' && liveTime !== null && liveFrame !== null ? (
              <div className="flex items-center gap-8 mb-4">
                <div className="flex items-center gap-3">
                  <div className="w-3 h-3 bg-blue-500 rounded-full shadow-lg shadow-blue-500/50"></div>
                  <span className="text-gray-300 font-medium">Time:</span>
                  <span className="text-blue-400 font-mono text-lg font-bold">{liveTime}s</span>
                </div>
                <div className="w-px h-6 bg-gray-500"></div>
                <div className="flex items-center gap-3">
                  <div className="w-3 h-3 bg-green-500 rounded-full shadow-lg shadow-green-500/50"></div>
                  <span className="text-gray-300 font-medium">Frame:</span>
                  <span className="text-green-400 font-mono text-lg font-bold">{liveFrame}</span>
                </div>
              </div>
            ) : (
              (secStr || frameStr || currentVideoTime !== null || selectedKeyframe) && (
                <div className="flex items-center gap-8 mb-4">
                  <div className="flex items-center gap-3">
                    <div className="w-3 h-3 bg-blue-500 rounded-full shadow-lg shadow-blue-500/50"></div>
                    <span className="text-gray-300 font-medium">Time:</span>
                    <span className="text-blue-400 font-mono text-lg font-bold">{displayTime}s</span>
                  </div>
                  <div className="w-px h-6 bg-gray-500"></div>
                  <div className="flex items-center gap-3">
                    <div className="w-3 h-3 bg-green-500 rounded-full shadow-lg shadow-green-500/50"></div>
                    <span className="text-gray-300 font-medium">Frame:</span>
                    <span className="text-green-400 font-mono text-lg font-bold">{displayFrame}</span>
                  </div>
                </div>
              )
            )}
            
            {/* Path Info */}
            <div className="flex items-start gap-3">
              <div className="flex items-center gap-2 mt-1">
                <div className="w-2 h-2 bg-yellow-500 rounded-full shadow-lg shadow-yellow-500/50"></div>
                <span className="text-gray-400 font-medium text-md">Path:</span>
              </div>
              <div className="text-yellow-400 mt-2 text-md font-mono leading-tight break-all flex-1">
                {viewMode === 'video' 
                  ? (selectedKeyframe?.imgpath || fullScreenImg.imgpath || "No image available")
                  : (selectedKeyframe?.imgpath || fullScreenImg.imgpath || "No image available")
                }
              </div>
            </div>
          </div>
        </div>

        {/* Sidebar */}
        <div
          onClick={(e) => e.stopPropagation()}
          className="max-h-[90vh] w-[380px] bg-gradient-to-b from-gray-900 via-gray-800 to-gray-900 rounded-2xl shadow-2xl overflow-hidden border border-gray-700 flex flex-col flex-shrink-0"
        >
          {/* Sidebar Header */}
          <div className="p-6 border-b border-gray-600/50 bg-gradient-to-r from-gray-800/80 to-gray-700/80 flex-shrink-0">
            <div className="flex items-center gap-3">
              <div className="w-4 h-4 bg-purple-500 rounded-full shadow-lg shadow-purple-500/50"></div>
              <h3 className="text-white font-bold text-xl">Những Keyframe liên quan</h3>
            </div>
          </div>
          
          {/* Keyframes Grid */}
          <div className="flex-1 overflow-y-auto custom-scrollbar">
            <div className="p-5">
              {Array.isArray(relatedObj?.near_keyframes) && relatedObj.near_keyframes.length > 0 ? (
                <div className="space-y-4">
                  {relatedObj.near_keyframes.map((image, idx) => (
                    <div key={image?.id ?? idx} className="group relative">
                      <div className={`relative overflow-hidden rounded-xl transition-all duration-300 cursor-pointer transform hover:scale-105 ${
                        selectedKeyframe?.id === image?.id 
                          ? 'ring-3 ring-blue-500 shadow-lg shadow-blue-500/25' 
                          : 'hover:ring-2 hover:ring-gray-400/50'
                      }`}>
                        <ImageListRelated 
                          image={image} 
                          onClick={handleKeyframeClick}
                          isSelected={selectedKeyframe?.id === image?.id}
                        />
                        {/* Selection Indicator */}
                        {selectedKeyframe?.id === image?.id && (
                          <div className="absolute top-2 right-2 w-6 h-6 bg-blue-500 rounded-full flex items-center justify-center shadow-lg">
                            <svg className="w-4 h-4 text-white" fill="currentColor" viewBox="0 0 20 20">
                              <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                            </svg>
                          </div>
                        )}
                        {/* Index Badge */}
                        <div className="absolute bottom-2 left-2 bg-black/80 text-white text-xs font-bold px-2 py-1 rounded-md">
                          #{idx + 1}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center h-full min-h-[300px] text-gray-400">
                  <div className="w-16 h-16 bg-gray-700 rounded-full flex items-center justify-center mb-4">
                    <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                    </svg>
                  </div>
                  <p className="text-center font-medium">Không có keyframes liên quan</p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Custom Scrollbar Styles */}
      <style jsx>{`
        .custom-scrollbar::-webkit-scrollbar {
          width: 10px;
        }
        .custom-scrollbar::-webkit-scrollbar-track {
          background: rgba(31, 41, 55, 0.4);
          border-radius: 6px;
          margin: 4px;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb {
          background: linear-gradient(180deg, rgba(107, 114, 128, 0.8) 0%, rgba(75, 85, 99, 0.9) 100%);
          border-radius: 6px;
          border: 1px solid rgba(55, 65, 81, 0.3);
        }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover {
          background: linear-gradient(180deg, rgba(107, 114, 128, 1) 0%, rgba(75, 85, 99, 1) 100%);
        }
      `}</style>
    </div>
  );
}
