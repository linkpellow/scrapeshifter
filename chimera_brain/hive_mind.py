"""
The Hive Mind - Shared Vector Memory (RAG for Action)

This module implements "Vector Experience Replay" - a collective intelligence
that remembers successful solutions and reuses them across all bot instances.

The Logic: We don't just "remember" cookies. We remember Situations.

How it works:
1. Bot #1 sees a screen, generates an embedding (visual/code state fingerprint)
2. Bot #1 solves the problem
3. Bot #1 saves (State_Embedding, Successful_Action) to Vector DB
4. Bot #2 sees a similar screen, queries the DB
5. Bot #2 executes the perfect solution in 10ms with Zero AI Inference

Result: The swarm gets smarter with every request.
"""

import json
import numpy as np
from typing import Optional, Dict, Any, List
from sentence_transformers import SentenceTransformer
import redis
from redis.commands.search.field import VectorField, TextField
from redis.commands.search.indexDefinition import IndexDefinition, IndexType
from redis.commands.search.query import Query
import logging

logger = logging.getLogger(__name__)


class HiveMind:
    """
    The Hive Mind - Shared memory for the Chimera Swarm
    
    Uses vector embeddings to cache successful action plans,
    allowing subsequent bots to skip expensive VLM inference.
    """
    
    def __init__(self, redis_client: Optional[redis.Redis] = None, redis_url: str = "redis://localhost:6379"):
        """
        Initialize the Hive Mind with Redis vector database
        
        Args:
            redis_client: Optional Redis client (if None, creates new connection)
            redis_url: Redis connection URL
        """
        if redis_client is None:
            self.redis = redis.from_url(redis_url, decode_responses=False)
        else:
            self.redis = redis_client
        
        # Load embedding model (lightweight, fast)
        # Using a small model for speed - can upgrade to larger models if needed
        logger.info("Loading embedding model for Hive Mind...")
        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')  # 80MB, ~50ms per embedding
        logger.info("Embedding model loaded")
        
        # Initialize vector index if it doesn't exist
        self._ensure_index()
    
    def _ensure_index(self):
        """Create Redis Search index for vector similarity search"""
        try:
            # Check if index exists
            self.redis.ft("experiences").info()
            logger.info("Hive Mind index already exists")
        except:
            # Create index
            logger.info("Creating Hive Mind vector index...")
            schema = (
                VectorField(
                    "vector",
                    "FLAT",
                    {
                        "TYPE": "FLOAT32",
                        "DIM": 384,  # all-MiniLM-L6-v2 dimension
                        "DISTANCE_METRIC": "COSINE"
                    }
                ),
                TextField("action_plan"),
                TextField("ax_tree_summary"),
                TextField("screenshot_hash"),
            )
            
            definition = IndexDefinition(prefix=["experience:"], index_type=IndexType.HASH)
            self.redis.ft("experiences").create_index(schema, definition=definition)
            logger.info("Hive Mind index created")
    
    def _generate_embedding(self, ax_tree_summary: str, screenshot_hash: str) -> np.ndarray:
        """
        Generate embedding for current state
        
        Args:
            ax_tree_summary: Text summary of AX tree structure
            screenshot_hash: Hash of screenshot (for exact matches)
        
        Returns:
            Embedding vector (384-dimensional)
        """
        # Combine AX tree and screenshot hash for embedding
        # The AX tree provides semantic structure, screenshot hash provides visual fingerprint
        combined_text = f"{ax_tree_summary}\n{screenshot_hash[:16]}"
        
        embedding = self.embedding_model.encode(combined_text, convert_to_numpy=True)
        return embedding
    
    def recall_experience(
        self, 
        ax_tree_summary: str, 
        screenshot_hash: str
    ) -> Optional[Dict[str, Any]]:
        """
        Query the Hive Mind: 'Have we solved a screen like this before?'
        
        Args:
            ax_tree_summary: Text summary of current AX tree
            screenshot_hash: Hash of current screenshot
        
        Returns:
            Cached action plan if found (similarity > 98%), None otherwise
        """
        try:
            # Generate embedding for current state
            embedding = self._generate_embedding(ax_tree_summary, screenshot_hash)
            
            # Search for similar experiences (KNN with cosine distance)
            # We use K=1 to get the single best match
            query = (
                Query("*=>[KNN 1 @vector $blob AS score]")
                .return_field("action_plan")
                .return_field("ax_tree_summary")
                .return_field("score")
                .dialect(2)
            )
            
            result = self.redis.ft("experiences").search(
                query,
                query_params={"blob": embedding.astype(np.float32).tobytes()}
            )
            
            # Check if we have a high-confidence match
            # Cosine distance < 0.1 means >98% similarity
            if result.docs and len(result.docs) > 0:
                score = float(result.docs[0].score)
                if score < 0.1:  # High similarity threshold
                    logger.info(f"🧠 HIVE MIND: Found cached solution (similarity: {1-score:.2%})")
                    action_plan = json.loads(result.docs[0].action_plan)
                    return action_plan
            
            logger.debug("Hive Mind: No cached solution found, must think for ourselves")
            return None
            
        except Exception as e:
            logger.warning(f"Hive Mind query failed (non-fatal): {e}")
            return None
    
    def store_experience(
        self,
        ax_tree_summary: str,
        screenshot_hash: str,
        action_plan: Dict[str, Any],
        success: bool = True
    ):
        """
        Store a successful experience in the Hive Mind
        
        Args:
            ax_tree_summary: Text summary of AX tree
            screenshot_hash: Hash of screenshot
            action_plan: The action plan that succeeded
            success: Whether the action succeeded (for filtering)
        """
        try:
            # Generate embedding
            embedding = self._generate_embedding(ax_tree_summary, screenshot_hash)
            
            # Create experience key
            experience_id = f"experience:{screenshot_hash}"
            
            # Store in Redis
            self.redis.hset(
                experience_id,
                mapping={
                    "vector": embedding.astype(np.float32).tobytes(),
                    "action_plan": json.dumps(action_plan),
                    "ax_tree_summary": ax_tree_summary[:1000],  # Truncate if too long
                    "screenshot_hash": screenshot_hash,
                    "success": "1" if success else "0",
                }
            )
            
            logger.info(f"🧠 HIVE MIND: Stored experience {screenshot_hash[:16]}...")
            
        except Exception as e:
            logger.warning(f"Failed to store experience in Hive Mind (non-fatal): {e}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get Hive Mind statistics"""
        try:
            info = self.redis.ft("experiences").info()
            return {
                "index_exists": True,
                "num_documents": info.get("num_docs", 0),
                "index_name": "experiences"
            }
        except:
            return {
                "index_exists": False,
                "num_documents": 0,
                "index_name": "experiences"
            }
