"""PostgreSQL Custom Types Example: tsvector and pgvector.

This example demonstrates how to register and use PostgreSQL-specific
types (tsvector for full-text search and pgvector for vector similarity)
in SQLObjects.

Requirements:
    - PostgreSQL database
    - pg_trgm extension (for tsvector)
    - pgvector extension (for vector operations)

Install pgvector:
    CREATE EXTENSION vector;
"""

from sqlalchemy.types import UserDefinedType

from sqlobjects.fields import Column, column
from sqlobjects.fields.types.comparators import DefaultComparator
from sqlobjects.fields.types.registry import register_field_type
from sqlobjects.model import ObjectModel


# ============================================================================
# Type Definitions
# ============================================================================


class TSVECTOR(UserDefinedType):
    """PostgreSQL tsvector type for full-text search."""

    cache_ok = True

    def get_col_spec(self, **kw):
        return "TSVECTOR"


class PGVECTOR(UserDefinedType):
    """PostgreSQL vector type for pgvector extension."""

    cache_ok = True

    def __init__(self, dimensions: int = 1536):
        self.dimensions = dimensions

    def get_col_spec(self, **kw):
        return f"VECTOR({self.dimensions})"


# ============================================================================
# Comparators
# ============================================================================


class TSVectorComparator(DefaultComparator):
    """Comparator for tsvector full-text search operations."""

    def match(self, query: str):  # type: ignore[reportIncompatibleMethodOverride]
        """Full-text search using @@ operator.

        Args:
            query: tsquery string (e.g., "python & programming")

        Returns:
            Boolean expression for filtering
        """
        from sqlalchemy import func

        return func.to_tsquery(query).op("@@")(self)


class PGVectorComparator(DefaultComparator):
    """Comparator for pgvector similarity operations."""

    def l2_distance(self, other):
        """L2 (Euclidean) distance using <-> operator.

        Args:
            other: Vector to compare against

        Returns:
            Distance expression for ordering/filtering
        """
        return self.op("<->")(other)

    def cosine_distance(self, other):
        """Cosine distance using <=> operator.

        Args:
            other: Vector to compare against

        Returns:
            Distance expression for ordering/filtering
        """
        return self.op("<=>")(other)

    def inner_product(self, other):
        """Inner product using <#> operator.

        Args:
            other: Vector to compare against

        Returns:
            Product expression for ordering/filtering
        """
        return self.op("<#>")(other)


# ============================================================================
# Register Types
# ============================================================================

# Use register_field_type() to register custom types
register_field_type(TSVECTOR, "tsvector", comparator=TSVectorComparator)
register_field_type(
    PGVECTOR, "pgvector", comparator=PGVectorComparator, aliases=["vector"], default_params={"dimensions": 1536}
)


# ============================================================================
# Models
# ============================================================================


class Document(ObjectModel):
    """Document model with full-text search and vector embeddings."""

    title: Column[str] = column(type="string", length=200)
    content: Column[str] = column(type="text")
    content_vector: Column = column(type="tsvector")
    embedding: Column = column(type="pgvector", dimensions=1536)

    class Config:
        table_name = "documents"


# ============================================================================
# Usage Examples
# ============================================================================


async def setup_database():
    """Setup database with required extensions."""
    from sqlobjects.database import create_tables, init_db
    from sqlobjects.session import get_session

    # Initialize database
    await init_db("postgresql+asyncpg://user:pass@localhost/mydb")

    # Enable extensions
    session = get_session(readonly=False)
    await session.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    await session.execute("CREATE EXTENSION IF NOT EXISTS vector")
    await session.commit()

    # Create tables
    await create_tables(ObjectModel)


async def full_text_search_examples():
    """Examples of full-text search using tsvector."""

    # Simple search
    docs = await Document.objects.filter(Document.content_vector.match("python")).all()
    print(f"Found {len(docs)} documents matching 'python'")

    # AND search
    docs = await Document.objects.filter(Document.content_vector.match("python & programming")).all()
    print(f"Found {len(docs)} documents matching 'python AND programming'")

    # OR search
    docs = await Document.objects.filter(Document.content_vector.match("python | javascript")).all()
    print(f"Found {len(docs)} documents matching 'python OR javascript'")

    # With ordering and pagination
    docs = (
        await Document.objects.filter(Document.content_vector.match("database")).order_by("-created_at").limit(10).all()
    )
    print("Top 10 recent documents about 'database'")


async def vector_similarity_examples():
    """Examples of vector similarity search using pgvector."""

    # Query vector (e.g., from OpenAI embeddings)
    query_vector = [0.1] * 1536  # Replace with actual embedding

    # L2 distance search
    similar_docs = (
        await Document.objects.annotate(distance=Document.embedding.l2_distance(query_vector))
        .order_by("distance")
        .limit(5)
        .all()
    )

    print("Top 5 similar documents (L2 distance):")
    for doc in similar_docs:
        print(f"  {doc.title}: distance={doc.distance:.4f}")

    # Cosine distance search
    similar_docs = (
        await Document.objects.annotate(distance=Document.embedding.cosine_distance(query_vector))
        .order_by("distance")
        .limit(5)
        .all()
    )

    print("\nTop 5 similar documents (cosine distance):")
    for doc in similar_docs:
        print(f"  {doc.title}: distance={doc.distance:.4f}")

    # Filter by distance threshold
    nearby_docs = await Document.objects.filter(Document.embedding.l2_distance(query_vector) < 0.5).all()
    print(f"\nFound {len(nearby_docs)} documents within distance 0.5")


async def combined_search_example():
    """Combine full-text search with vector similarity."""

    query_vector = [0.1] * 1536

    # First filter by full-text, then rank by similarity
    results = (
        await Document.objects.filter(Document.content_vector.match("python & machine learning"))
        .annotate(similarity=Document.embedding.l2_distance(query_vector))
        .order_by("similarity")
        .limit(10)
        .all()
    )

    print("Top 10 relevant documents (text + semantic):")
    for doc in results:
        print(f"  {doc.title}: similarity={doc.similarity:.4f}")


async def create_sample_data():
    """Create sample documents with embeddings."""
    import random

    documents = [
        {
            "title": "Introduction to Python",
            "content": "Python is a high-level programming language...",
            "content_vector": "to_tsvector('english', 'Python is a high-level programming language')",
            "embedding": [random.random() for _ in range(1536)],
        },
        {
            "title": "Machine Learning Basics",
            "content": "Machine learning is a subset of artificial intelligence...",
            "content_vector": "to_tsvector('english', 'Machine learning is a subset of artificial intelligence')",
            "embedding": [random.random() for _ in range(1536)],
        },
        {
            "title": "Database Design Patterns",
            "content": "Database design patterns help structure data efficiently...",
            "content_vector": "to_tsvector('english', 'Database design patterns help structure data efficiently')",
            "embedding": [random.random() for _ in range(1536)],
        },
    ]

    # Note: In production, use proper text-to-vector conversion
    # and actual embeddings from models like OpenAI
    for doc_data in documents:
        await Document.objects.create(**doc_data)

    print(f"Created {len(documents)} sample documents")


async def main():
    """Run all examples."""
    print("Setting up database...")
    await setup_database()

    print("\nCreating sample data...")
    await create_sample_data()

    print("\n" + "=" * 60)
    print("Full-Text Search Examples")
    print("=" * 60)
    await full_text_search_examples()

    print("\n" + "=" * 60)
    print("Vector Similarity Examples")
    print("=" * 60)
    await vector_similarity_examples()

    print("\n" + "=" * 60)
    print("Combined Search Example")
    print("=" * 60)
    await combined_search_example()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
