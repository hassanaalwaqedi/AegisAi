"""
Behavior Embeddings - Vector representations of user behavior
"""

from dataclasses import dataclass
import numpy as np
from typing import Optional


@dataclass
class BehaviorVector:
    """Vector representation of user behavior for clustering"""
    session_id: str
    embedding: np.ndarray
    cluster_id: Optional[int] = None
    
    def similarity(self, other: 'BehaviorVector') -> float:
        """Cosine similarity with another behavior vector"""
        dot = np.dot(self.embedding, other.embedding)
        norm_a = np.linalg.norm(self.embedding)
        norm_b = np.linalg.norm(other.embedding)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(dot / (norm_a * norm_b))


class BehaviorEmbeddings:
    """Generate and manage behavior embeddings for user clustering"""
    
    FEATURE_DIMS = 12
    
    def __init__(self):
        self._vectors: dict[str, BehaviorVector] = {}
    
    def generate_embedding(self, session_summary: dict) -> np.ndarray:
        """Generate embedding from session summary"""
        features = np.zeros(self.FEATURE_DIMS, dtype=np.float32)
        
        # Engagement features
        features[0] = min(session_summary.get("scroll_depth_max", 0), 1.0)
        features[1] = min(session_summary.get("event_count", 0) / 100, 1.0)
        features[2] = min(session_summary.get("decision_path_length", 0) / 20, 1.0)
        
        # Frustration signals
        features[3] = min(session_summary.get("rage_clicks", 0) / 10, 1.0)
        features[4] = min(session_summary.get("hesitation_count", 0) / 10, 1.0)
        
        # Intent one-hot encoding
        intent = session_summary.get("intent", "exploring")
        intent_map = {
            "exploring": 5, "comparing": 6, "deciding": 7,
            "confused": 8, "frustrated": 9, "engaged": 10
        }
        if intent in intent_map:
            features[intent_map[intent]] = 1.0
        
        # Normalize
        norm = np.linalg.norm(features)
        if norm > 0:
            features = features / norm
        
        return features
    
    def add_session(self, session_id: str, session_summary: dict) -> BehaviorVector:
        """Add session to embedding space"""
        embedding = self.generate_embedding(session_summary)
        vector = BehaviorVector(session_id=session_id, embedding=embedding)
        self._vectors[session_id] = vector
        return vector
    
    def find_similar(self, session_id: str, top_k: int = 5) -> list[tuple[str, float]]:
        """Find similar sessions by behavior"""
        if session_id not in self._vectors:
            return []
        
        target = self._vectors[session_id]
        similarities = []
        
        for sid, vector in self._vectors.items():
            if sid != session_id:
                sim = target.similarity(vector)
                similarities.append((sid, sim))
        
        similarities.sort(key=lambda x: x[1], reverse=True)
        return similarities[:top_k]
    
    def cluster_sessions(self, n_clusters: int = 5) -> dict[int, list[str]]:
        """Simple k-means clustering of sessions"""
        if len(self._vectors) < n_clusters:
            return {0: list(self._vectors.keys())}
        
        # Simple centroid-based clustering
        embeddings = np.array([v.embedding for v in self._vectors.values()])
        sessions = list(self._vectors.keys())
        
        # Initialize centroids randomly
        indices = np.random.choice(len(sessions), n_clusters, replace=False)
        centroids = embeddings[indices].copy()
        
        # Iterate
        for _ in range(10):
            # Assign clusters
            clusters: dict[int, list[int]] = {i: [] for i in range(n_clusters)}
            for idx, emb in enumerate(embeddings):
                distances = [np.linalg.norm(emb - c) for c in centroids]
                cluster_id = int(np.argmin(distances))
                clusters[cluster_id].append(idx)
                self._vectors[sessions[idx]].cluster_id = cluster_id
            
            # Update centroids
            for cid, members in clusters.items():
                if members:
                    centroids[cid] = embeddings[members].mean(axis=0)
        
        return {cid: [sessions[i] for i in members] for cid, members in clusters.items()}
