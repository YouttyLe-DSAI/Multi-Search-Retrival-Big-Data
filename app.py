import os
import mimetypes
import copy
import json
from pathlib import Path
import numpy as np
from flask_cors import CORS
from flask import Flask, request, jsonify, send_file, abort
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from utils.parse_frontend import parse_data
from utils.faiss_processing import MyFaiss
from utils.context_encoding import VisualEncoding
from utils.semantic_embed.tag_retrieval import tag_retrieval
from utils.combine_utils import merge_searching_results_by_addition
from utils.search_utils import group_result_by_video, search_by_filter
from flask import request, has_request_context
# ================= Helpers =================

# Thư mục vật lý chứa keyframes
BASE_KEYFRAMES_DIR = Path(os.environ.get(
    "KEYFRAMES_DIR",
    r"./frontend/ai/public/data/Keyframes"
)).resolve()

# Thư mục vật lý chứa video files
BASE_VIDEO_DIR = Path(os.environ.get(
    "VIDEO_DIR",
    r"./AIC_Video"
)).resolve()

# Base URL backend (để trả URL tuyệt đối cho <img src>)
BACKEND_BASE = os.environ.get("BACKEND_BASE_URL", "http://localhost:5001")

def _parse_keyframe_path(img_path: str):
    """Trả về (data_part, video_id, frame_id_stem) từ đường dẫn keyframe."""
    p = Path(img_path)
    parts = p.parts
    k = None
    for i, seg in enumerate(parts):
        if seg.lower() == "keyframes":
            k = i
            break
    tail = parts[k + 1:] if k is not None else parts
    stem = Path(tail[-1]).stem if tail else p.stem
    if len(tail) >= 3:
        data_part, video_id, frame_id = tail[-3], tail[-2], stem
    else:
        data_part = p.parent.parent.name if p.parent and p.parent.parent else ""
        video_id = p.parent.name if p.parent else ""
        frame_id = p.stem
    return data_part, video_id, frame_id

def _safe_map_frame_id(key: str, frame_id_stem: str, KeyframesMapper):
    """Giữ nguyên nếu không có mapper; chỉ dùng cho shot view."""
    try:
        if KeyframesMapper and key in KeyframesMapper:
            fid = str(int(frame_id_stem))
            return KeyframesMapper[key].get(fid, frame_id_stem)
    except Exception:
        pass
    return frame_id_stem

def _subpath_under_keyframes(img_path: str) -> str:
    """Lấy subpath dưới 'Keyframes' cho ảnh (chuẩn hoá Win/Linux)."""
    p = str(img_path).replace("\\", "/")
    if "Keyframes/" in p:
        return p.split("Keyframes/")[-1]
    parts = [seg for seg in p.strip("/").split("/") if seg]
    return "/".join(parts[-2:])  # fallback

def path_to_url(img_path: str) -> str:
    """Trả về absolute URL khớp đúng host/proto (kể cả khi qua ngrok)."""
    sub = _subpath_under_keyframes(img_path)
    if has_request_context():
        proto = request.headers.get("X-Forwarded-Proto", request.scheme)
        host  = request.headers.get("X-Forwarded-Host", request.host)
        base  = f"{proto}://{host}"
    else:
        # Fallback khi chạy ngoài request (hầu như không dùng đến)
        base = BACKEND_BASE
    return f"{base.rstrip('/')}/keyframe/{sub}"

def get_local_video_url(video_id: str) -> str:
    """Tạo URL để serve video local thay vì YouTube."""
    if has_request_context():
        proto = request.headers.get("X-Forwarded-Proto", request.scheme)
        host  = request.headers.get("X-Forwarded-Host", request.host)
        base  = f"{proto}://{host}"
    else:
        base = BACKEND_BASE
    return f"{base.rstrip('/')}/video/{video_id}"

def find_video_file(video_id: str):
    """Tìm file video trong thư mục VIDEO theo video_id (K02_V019, L22_V002, v.v.)"""
    # Tìm trực tiếp trong thư mục VIDEO với các định dạng phổ biến
    for ext in ['.mp4', '.avi', '.mov', '.mkv', '.webm']:
        # Thử với tên đầy đủ video_id (K02_V019, L22_V002, ...)
        video_path = BASE_VIDEO_DIR / f"{video_id}{ext}"
        if video_path.exists():
            return video_path
        
        # Thử với tên rút gọn (chỉ phần sau dấu _)
        parts = video_id.split('_')
        if len(parts) >= 2:
            video_name = parts[1]  # V019, V002, etc.
            video_path = BASE_VIDEO_DIR / f"{video_name}{ext}"
            if video_path.exists():
                return video_path
    return None

def postprocess_result_urls(data_list):
    """Đổi toàn bộ lst_keyframe_paths sang URL để <img src> dùng được."""
    for item in data_list:
        vi = item.get("video_info", {})
        if "lst_keyframe_paths" in vi:
            vi["lst_keyframe_paths"] = [path_to_url(p) for p in vi["lst_keyframe_paths"]]
    return data_list

def enrich_groups_with_meta(groups):
    """Bơm sec & frame_idx (đúng từ id2img_fps.json) vào kết quả nhóm theo video."""
    for g in groups:
        vi = g.get('video_info', {})
        idxs = vi.get('lst_idxs', [])
        secs, frames = [], []
        for sid in idxs:
            info = DictImagePath.get(int(sid))
            secs.append(None if not info else info.get('sec'))
            frames.append(None if not info else info.get('frame_idx'))
        vi['lst_keyframe_secs']   = secs
        vi['lst_frame_numbers']   = frames
    return groups

# Gắn tham số thời gian đơn giản, giữ URL gốc (không đổi watch <-> youtu.be)
YT_TIME_KEYS = {'t', 'start', 'time_continue', 'timestart'}
def build_seek_url(video_url: str, start_sec=None):
    base = str(video_url)
    if start_sec is None:
        return base, None
    # giữ thập phân theo đúng json
    s_str = str(float(start_sec)).rstrip('0').rstrip('.') if '.' in str(start_sec) else str(start_sec)

    low = base.lower()
    scheme, netloc, path, query, frag = urlsplit(base)
    # xoá tham số thời gian cũ
    q = [(k, v) for (k, v) in parse_qsl(query, keep_blank_values=True) if k not in YT_TIME_KEYS]

    if "youtube.com/embed" in low:
        # embed chỉ nhận int
        q.append(("start", str(int(float(s_str)))))
    else:
        q.append(("t", f"{s_str}s"))

    return urlunsplit((scheme, netloc, path, urlencode(q, doseq=True), frag)), s_str

# ================== Config & Objects ==================

json_path = 'dict/id2img_fps.json'
audio_json_path = 'dict/audio_id2img_id.json'
img2audio_json_path = 'dict/img_id2audio_id.json'
scene_path = 'dict/scene_id2info.json'
map_keyframes_path = 'dict/map_keyframes.json'
video_division_path = 'dict/video_division_tag.json'
video_id2img_path = 'dict/video_id2img_id.json'
bin_clip_file = 'dict/faiss_clip_cosine.bin'
bin_clipv2_file = 'dict/faiss_clipv2_cosine.bin'

VisualEncoder = VisualEncoding()
CosineFaiss = MyFaiss(bin_clip_file, bin_clipv2_file, json_path, audio_json_path, img2audio_json_path)
TagRecommendation = tag_retrieval()
DictImagePath = CosineFaiss.id2img_fps
TotalIndexList = np.array(list(range(len(DictImagePath)))).astype('int64')

with open(scene_path, 'r', encoding='utf-8') as f:
    Sceneid2info = json.load(f)
with open(map_keyframes_path, 'r', encoding='utf-8') as f:
    KeyframesMapper = json.load(f)
with open(video_division_path, 'r', encoding='utf-8') as f:
    VideoDivision = json.load(f)
with open(video_id2img_path, 'r', encoding='utf-8') as f:
    Videoid2imgid = json.load(f)

def get_search_space(id):
    search_space = []
    video_space = VideoDivision[f'list_{id}']
    for video_id in video_space:
        search_space.extend(Videoid2imgid[video_id])
    return search_space

SearchSpace = {i: np.array(get_search_space(i)).astype('int64') for i in range(1, 5)}
SearchSpace[0] = TotalIndexList

def get_near_frame(idx):
    image_info = DictImagePath[idx]
    scene_idx = image_info['scene_idx'].split('/')
    return copy.deepcopy(
        Sceneid2info[scene_idx[0]][scene_idx[1]][scene_idx[2]][scene_idx[3]]['lst_keyframe_idxs']
    )

def get_related_ignore(ignore_index):
    total_ignore_index = []
    for idx in ignore_index:
        total_ignore_index.extend(get_near_frame(idx))
    return total_ignore_index

# ================== Flask ==================
app = Flask(__name__, template_folder='templates')
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=False)

@app.after_request
def _add_cors_headers(resp):
    resp.headers['Access-Control-Allow-Origin'] = '*'
    # thêm header ngrok-skip-browser-warning để preflight pass
    resp.headers['Access-Control-Allow-Headers'] = (
        'Content-Type, Authorization, X-Requested-With, ngrok-skip-browser-warning'
    )
    resp.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
    return resp


# ---- Static serving for keyframes ----
@app.route("/keyframe/<path:subpath>")
def serve_keyframe(subpath):
    target = (BASE_KEYFRAMES_DIR / subpath).resolve()
    try:
        target.relative_to(BASE_KEYFRAMES_DIR)
    except Exception:
        return abort(403)
    if not target.exists() or not target.is_file():
        return abort(404)
    mt = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
    return send_file(str(target), mimetype=mt)

# ---- Static serving for videos ----
@app.route("/video/<video_id>")
def serve_video(video_id):
    video_path = find_video_file(video_id)
    if not video_path or not video_path.exists():
        return abort(404)
    
    # Kiểm tra security - đảm bảo file nằm trong BASE_VIDEO_DIR
    try:
        video_path.resolve().relative_to(BASE_VIDEO_DIR)
    except Exception:
        return abort(403)
    
    # Support range requests cho video streaming
    def generate():
        with open(video_path, 'rb') as f:
            data = f.read(1024)
            while data:
                yield data
                data = f.read(1024)
    
    mt = mimetypes.guess_type(str(video_path))[0] or "video/mp4"
    return app.response_class(generate(), mimetype=mt, headers={
        'Accept-Ranges': 'bytes',
        'Content-Length': str(video_path.stat().st_size)
    })

@app.route('/data')
def index():
    pagefile, count = [], 0
    for sid, value in DictImagePath.items():
        pagefile.append({'imgpath': path_to_url(value['image_path']), 'id': sid})
        count += 1
        if count >= 500:
            break
    return jsonify({'pagefile': pagefile})

@app.route('/imgsearch')
def image_search():
    k = int(request.args.get('k'))
    id_query = int(request.args.get('imgid'))
    lst_scores, list_ids, _, list_image_paths = CosineFaiss.image_search(id_query, k=k)
    data = group_result_by_video(lst_scores, list_ids, list_image_paths, KeyframesMapper)
    data = enrich_groups_with_meta(data)
    data = postprocess_result_urls(data)
    return jsonify(data)

@app.route('/getquestions', methods=['POST', 'OPTIONS'], strict_slashes=False)
def get_questions():
    if request.method == 'OPTIONS':
        return ('', 204)
    return jsonify([])  # FE setQuestions(res)

@app.route('/getignore', methods=['POST', 'OPTIONS'], strict_slashes=False)
def get_ignore():
    if request.method == 'OPTIONS':
        return ('', 204)
    return jsonify({'data': []})

@app.route('/socket.io/', methods=['GET', 'POST', 'OPTIONS'], strict_slashes=False)
def socketio_stub():
    if request.method == 'OPTIONS':
        return ('', 204)
    # Trả rỗng 200 là đủ để client ngừng báo lỗi, không implement Socket.IO thật
    return ('', 200)


@app.route('/textsearch', methods=['POST', 'OPTIONS'], strict_slashes=False)
def text_search():
    if request.method == 'OPTIONS':
        return ('', 204)
    data = request.get_json(silent=True) or {}

    search_space_index = int(data['search_space'])
    k = int(data['k'])
    clip = data['clip']
    clipv2 = data['clipv2']
    text_query = data['textquery']
    range_filter = int(data['range_filter'])

    index = None
    if data.get('filter'):
        index = np.array(data['id']).astype('int64')
        k = min(k, len(index))

    keep_index = None
    ignore_index = None
    if data.get('ignore'):
        ignore_index = get_related_ignore(np.array(data['ignore_idxs']).astype('int64'))
        keep_index = np.delete(TotalIndexList, ignore_index)

    if keep_index is not None:
        index = np.intersect1d(index, keep_index) if index is not None else keep_index

    index = SearchSpace[search_space_index] if index is None else np.intersect1d(index, SearchSpace[search_space_index])
    k = min(k, len(index))

    if clip and clipv2:
        model_type = 'both'
    elif clip:
        model_type = 'clip'
    else:
        model_type = 'clipv2'

    if data['filtervideo'] != 0:
        mode = data['filtervideo']
        prev_result = data['videos']
        data = search_by_filter(prev_result, text_query, k, mode, model_type, range_filter, ignore_index, keep_index,
                                Sceneid2info, DictImagePath, CosineFaiss, KeyframesMapper)
    else:
        if model_type == 'both':
            scores_clip, list_clip_ids, _, _ = CosineFaiss.text_search(text_query, index=index, k=k, model_type='clip')
            scores_clipv2, list_clipv2_ids, _, _ = CosineFaiss.text_search(text_query, index=index, k=k, model_type='clipv2')
            lst_scores, list_ids = merge_searching_results_by_addition([scores_clip, scores_clipv2],
                                                                       [list_clip_ids, list_clipv2_ids])
            kept_ids, kept_scores, kept_paths = [], [], []
            for sid, sc in zip(list_ids, lst_scores):
                info = DictImagePath.get(int(sid))
                if info and 'image_path' in info:
                    kept_ids.append(int(sid))
                    kept_scores.append(float(sc))
                    kept_paths.append(info['image_path'])
            lst_scores = np.array(kept_scores, dtype=np.float32)
            list_ids = np.array(kept_ids, dtype=np.int64)
            list_image_paths = kept_paths
        else:
            lst_scores, list_ids, _, list_image_paths = CosineFaiss.text_search(
                text_query, index=index, k=k, model_type=model_type
            )
        data = group_result_by_video(lst_scores, list_ids, list_image_paths, KeyframesMapper)

    data = enrich_groups_with_meta(data)
    data = postprocess_result_urls(data)
    return jsonify(data)

@app.route('/panel', methods=['POST', 'OPTIONS'], strict_slashes=False)
def panel():
    if request.method == 'OPTIONS':
        return ('', 204)
    search_items = request.get_json(silent=True) or {}
    k = int(search_items['k'])
    search_space_index = int(search_items['search_space'])

    index = None
    if search_items.get('useid'):
        index = np.array(search_items['id']).astype('int64')
        k = min(k, len(index))

    keep_index = None
    if search_items.get('ignore'):
        ignore_index = get_related_ignore(np.array(search_items['ignore_idxs']).astype('int64'))
        keep_index = np.delete(TotalIndexList, ignore_index)

    if keep_index is not None:
        index = np.intersect1d(index, keep_index) if index is not None else keep_index

    index = SearchSpace[search_space_index] if index is None else np.intersect1d(index, SearchSpace[search_space_index])
    k = min(k, len(index))

    object_input = parse_data(search_items, VisualEncoder)
    ocr_input = None if search_items['ocr'] == "" else search_items['ocr']
    asr_input = None if search_items['asr'] == "" else search_items['asr']

    semantic = False
    keyword = True
    lst_scores, list_ids, _, list_image_paths = CosineFaiss.context_search(
        object_input=object_input, ocr_input=ocr_input, asr_input=asr_input,
        k=k, semantic=semantic, keyword=keyword, index=index, useid=search_items['useid']
    )

    data = group_result_by_video(lst_scores, list_ids, list_image_paths, KeyframesMapper)
    data = enrich_groups_with_meta(data)
    data = postprocess_result_urls(data)
    return jsonify(data)

@app.route('/getrec', methods=['POST', 'OPTIONS'], strict_slashes=False)
def getrec():
    if request.method == 'OPTIONS':
        return ('', 204)
    k = 50
    text_query = request.get_json(silent=True)
    tag_outputs = TagRecommendation(text_query, k)
    return jsonify(tag_outputs)

@app.route('/relatedimg')
def related_img():
    # FE chỉ cần gửi imgid
    id_query = request.args.get('imgid', type=int)
    if id_query is None:
        return jsonify({})
    image_info = DictImagePath[id_query]           # có 'sec' & 'frame_idx'
    image_path = image_info['image_path']
    keyframe_sec = image_info.get('sec')

    scene_idx  = image_info['scene_idx'].split('/')
    video_info = copy.deepcopy(Sceneid2info[scene_idx[0]][scene_idx[1]])
    video_url  = video_info['video_metadata']['watch_url']
    shot_time  = video_info[scene_idx[2]][scene_idx[3]]['shot_time']

    # Lấy thông tin đầy đủ cho mỗi keyframe thay vì chỉ URL
    near_keyframes = []
    for img_path in video_info[scene_idx[2]][scene_idx[3]]['lst_keyframe_paths']:
        # Parse đường dẫn để lấy thông tin
        data_part, video_id, frame_id = _parse_keyframe_path(img_path)
        
        # Tìm thông tin từ DictImagePath nếu có
        keyframe_info = None
        for idx, info in DictImagePath.items():
            if info.get('image_path') == img_path:
                keyframe_info = {
                    'imgpath': path_to_url(img_path),
                    'sec': info.get('sec'),
                    'frame_idx': info.get('frame_idx'),
                    'id': idx
                }
                break
        
        # Nếu không tìm thấy, tạo thông tin cơ bản
        if not keyframe_info:
            keyframe_info = {
                'imgpath': path_to_url(img_path),
                'sec': None,
                'frame_idx': frame_id,
                'id': None
            }
        
        near_keyframes.append(keyframe_info)
    
    # Loại bỏ keyframe hiện tại
    try:
        near_keyframes = [k for k in near_keyframes if k['imgpath'] != path_to_url(image_path)]
    except ValueError:
        pass

    # Tạo video_id từ scene_idx để tìm video local
    # scene_idx[0] = L21, scene_idx[1] = V001 -> video_id = L21_V001
    local_video_id = f"{scene_idx[0]}_{scene_idx[1]}"
    local_video_url = get_local_video_url(local_video_id)
    
    # Kiểm tra xem video local có tồn tại không
    video_file_exists = find_video_file(local_video_id) is not None
    
    if video_file_exists:
        # Sử dụng video local
        final_video_url = local_video_url
        final_video_url_seek = local_video_url  # Local video không cần seek parameter
        is_local_video = True
    else:
        # Fallback về YouTube nếu không có video local
        seek_url, sec_sent = build_seek_url(video_url, start_sec=keyframe_sec)
        final_video_url = video_url
        final_video_url_seek = seek_url
        is_local_video = False

    return jsonify({
        'video_url': final_video_url,
        'video_url_seek': final_video_url_seek,
        'start_sec': keyframe_sec if is_local_video else sec_sent,
        'keyframe_sec': keyframe_sec,
        'frame_idx': image_info.get('frame_idx'),
        'video_range': shot_time,
        'near_keyframes': near_keyframes,
        'is_local_video': is_local_video,
        'local_video_id': local_video_id
    })

@app.route('/getvideoshot')
def get_video_shot():
    if request.args.get('imgid') == 'undefined':
        return jsonify({})
    id_query = int(request.args.get('imgid'))
    image_info = DictImagePath[id_query]
    scene_idx = image_info['scene_idx'].split('/')
    shots = copy.deepcopy(Sceneid2info[scene_idx[0]][scene_idx[1]][scene_idx[2]])

    selected_shot = int(scene_idx[3])
    total_n_shots = len(shots)
    new_shots = {}
    for select_id in range(max(0, selected_shot-5), min(selected_shot+6, total_n_shots)):
        new_shots[str(select_id)] = shots[str(select_id)]
    shots = new_shots

    for shot_key in list(shots.keys()):
        lst_keyframe_idxs = []
        url_paths = []
        for img_path in shots[shot_key]['lst_keyframe_paths']:
            data_part, video_id, frame_id = _parse_keyframe_path(img_path)
            key = f'{data_part}_{video_id}'.replace('_extra', '')
            if 'extra' not in data_part:
                frame_id = _safe_map_frame_id(key, frame_id, KeyframesMapper)
            try:
                frame_id_int = int(frame_id)
            except Exception:
                frame_id_int = frame_id
            lst_keyframe_idxs.append(frame_id_int)
            url_paths.append(path_to_url(img_path))

        shots[shot_key]['lst_idxs'] = shots[shot_key]['lst_keyframe_idxs']
        shots[shot_key]['lst_keyframe_secs'] = [DictImagePath[idx].get('sec') for idx in shots[shot_key]['lst_idxs']]
        shots[shot_key]['lst_frame_numbers'] = [DictImagePath[idx].get('frame_idx') for idx in shots[shot_key]['lst_idxs']]
        shots[shot_key]['lst_keyframe_idxs'] = lst_keyframe_idxs
        shots[shot_key]['lst_keyframe_paths'] = url_paths

    return jsonify({
        'collection': scene_idx[0],
        'video_id': scene_idx[1],
        'shots': shots,
        'selected_shot': scene_idx[3]
    })

@app.route('/feedback', methods=['POST', 'OPTIONS'], strict_slashes=False)
def feed_back():
    if request.method == 'OPTIONS':
        return ('', 204)
    data = request.get_json(silent=True) or {}
    k = int(data['k'])
    prev_result = data['videos']
    lst_pos_vote_idxs = data['lst_pos_idxs']
    lst_neg_vote_idxs = data['lst_neg_idxs']
    lst_scores, list_ids, _, list_image_paths = CosineFaiss.reranking(prev_result, lst_pos_vote_idxs, lst_neg_vote_idxs, k)
    data = group_result_by_video(lst_scores, list_ids, list_image_paths, KeyframesMapper)
    data = enrich_groups_with_meta(data)
    data = postprocess_result_urls(data)
    return jsonify(data)

@app.route('/translate', methods=['POST', 'OPTIONS'], strict_slashes=False)
def translate():
    if request.method == 'OPTIONS':
        return ('', 204)
    data = request.get_json(silent=True) or {}
    text_query = data['textquery']
    text_query_translated = CosineFaiss.translater(text_query)
    return jsonify(text_query_translated)

# Running app
if __name__ == '__main__':
    print(f"[KEYFRAMES_DIR] Serving from: {BASE_KEYFRAMES_DIR}")
    print(f"[BACKEND_BASE] {BACKEND_BASE}")
    app.run(host="0.0.0.0", port=5001, debug=False, use_reloader=False, threaded=True)
