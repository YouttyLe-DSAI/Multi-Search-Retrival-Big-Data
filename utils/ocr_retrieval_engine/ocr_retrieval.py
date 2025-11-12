import sys, os, pickle, numpy as np, scipy, re
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(script_dir, '..'))
grand_dir  = os.path.abspath(os.path.join(parent_dir, '..'))
sys.path.extend([parent_dir, grand_dir])

from utils.object_retrieval_engine.object_retrieval import load_file

def GET_PROJECT_ROOT():
    cur = os.path.abspath(__file__)
    while True:
        if os.path.split(cur)[1] == 'VN_Multi_User_Video_Search':
            return cur
        cur = os.path.dirname(cur)

PROJECT_ROOT = GET_PROJECT_ROOT()

class ocr_retrieval(load_file):
    def __init__(
        self,
        ocr_context_path='dict/ocr/*',
        ocr_embed_path=os.path.join(PROJECT_ROOT, 'dict/bin/ocr_bin'),
    ):
        os.makedirs(os.path.join(PROJECT_ROOT, 'dict/bin'), exist_ok=True)
        os.makedirs(ocr_embed_path, exist_ok=True)

        super().__init__(
            clean_data_path={'ocr': ocr_context_path},
            save_tfids_object_path=ocr_embed_path,
            all_datatpye=['ocr'],
            context_data=None,
            ngram_range=(1, 3),
            update=False,
            input_datatype='json'
        )
        with open(os.path.join(ocr_embed_path, 'tfidf_transform_ocr.pkl'), 'rb') as f:
            self.tfidf_transform_ocr = pickle.load(f)
        # FIX: không join PROJECT_ROOT lần nữa (tránh sai đường dẫn)
        self.context_sparse_matrix_ocr = scipy.sparse.load_npz(
            os.path.join(ocr_embed_path, 'sparse_context_matrix_ocr.npz')
        )

    def __call__(self, query: str, k: int, index=None):
        # TF-IDF retrieval
        ocr_tfidf_score, ocr_tfidf_index = self.get_tfidf_score(query.lower(), k, index)
        return ocr_tfidf_score, ocr_tfidf_index

    def get_tfidf_score(self, query: str, k: int, index):
        vec = self.tfidf_transform_ocr.transform([query])     # 1×V
        mat = self.context_sparse_matrix_ocr                  # N×V (CSR)
        n = mat.shape[0]

        # Lọc chỉ số hợp lệ để tránh IndexError
        if index is None:
            idx = np.arange(n, dtype=np.int64)
        else:
            idx = np.asarray(index, dtype=np.int64).ravel()
            idx = idx[(idx >= 0) & (idx < n)]

        if idx.size == 0:
            return np.empty(0, dtype=np.float32), np.empty(0, dtype=np.int64)

        k = min(k, idx.size)
        scores = vec.dot(mat[idx, :].T).toarray().ravel()     # 1×|idx| → |idx|

        # top-k nhanh & ổn định
        if scores.size > k:
            part = np.argpartition(-scores, k - 1)[:k]
            order = np.argsort(-scores[part])
            top_scores = scores[part][order]
            top_idx = idx[part][order]
        else:
            order = np.argsort(-scores)
            top_scores = scores[order]
            top_idx = idx[order]

        return top_scores.astype(np.float32), top_idx.astype(np.int64)

if __name__ == '__main__':
    obj = ocr_retrieval()
    score, index = obj("Dùng nuóc sát khẩn chúa Methanol nguy hiểm tói tính mạng", 3)
    print(score, index)
