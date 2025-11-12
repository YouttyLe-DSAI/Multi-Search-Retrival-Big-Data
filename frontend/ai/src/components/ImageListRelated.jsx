import React from "react";
import Image from "next/image";

function ImageListRelated({
  image,
  onClick,
  isSelected = false
}) {
  const handleClick = () => {
    if (onClick) {
      onClick(image);
    }
  };

  return (
    <li
      className={`m-0.5 group hover:ease-in-out group duration-300 bg-slate-300 p-0.5 h-max rounded-md flex relative mb-0.5 cursor-pointer transition-all ${
        isSelected ? 'ring-2 ring-blue-500 bg-blue-100' : 'hover:bg-slate-200'
      }`}
      onClick={handleClick}
      key={image?.id || image}
    >
      <div className="group relative flex h-[169px] w-full">
        <Image
          src={image?.imgpath || image}
          fill={true}
          className="hover:ease-in-out duration-300 relative rounded-md object-cover"
          alt="Keyframe"
        />
        {/* Hiển thị thời gian nếu có */}
        {image?.sec && (
          <div className="absolute bottom-1 right-1 bg-black bg-opacity-70 text-white text-xs px-1 py-0.5 rounded">
            {Math.floor(image.sec)}s
          </div>
        )}
      </div>
    </li>
  );
}

export default ImageListRelated;
