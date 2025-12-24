	• Retrieval-Augmented Generation (RAG) is the process of optimizing the output of a large language model, so it references an authoritative knowledge base outside of its training data sources before generating a response. 
	• Large Language Models (LLMs) are trained on vast volumes of data and use billions of parameters to generate original output for tasks like answering questions, translating languages, and completing sentences. 
	• Used leverage domain-specific or organizational knowledge bases, without requiring model retraining.

Raw Documents / Knowledge Sources
Sources:
	• PDFs
	• Confluence/Wiki pages
	• Jira tickets
	• API documentation
	• Internal policies
	• Excel sheets
Goal → Bring all knowledge into the system.

Text Splitter / Chunking Layer
	1. Converts the entire document into clean plain text
	2. Breaks the document into small, meaningful chunks
	3. Creates overlap between chunks
	4. Adds metadata to every chunk
	5. Prepares final chunk objects for embedding

	1. Converts the entire document into clean plain text
		a. Extracts text from PDFs, Word, Jira, Wiki, Websites, etc.
		b. Removes noise like headers, footers, page numbers.
		c. Normalizes the text (spaces, newlines, encoding fixes).
		d. → Purpose: Make the raw document usable for embeddings.
	
	2. Breaks the document into small, meaningful chunks
		a. Splits large documents into 300–500 token blocks.
		b. Uses rules like paragraphs, headings, or semantic boundaries.
			i. Break at a new paragraph (empty line, \n\n).
			ii. Break when you see a heading.
			iii. Break when the meaning shifts even if there is no heading.
		c. Why do we split?
			i. To avoid sending large documents directly to embeddings
			ii. To store meaningful units in vector DB
		d. → Purpose: LLMs and vector DB work best with small units of meaning.
	
	3. Creates overlap between chunks
		a. Adds 20–30% overlap to avoid losing context.
		b. Example:
			i. Chunk 1 = sentences 1–8
			ii. Chunk 2 = sentences 6–14
		c. → Purpose: Prevents missing important details at chunk boundaries.
	4. Adds metadata to every chunk
		a. Each chunk gets identifiers like:
			i. document name
			ii. section or heading
			iii. page number
			iv. source type (PDF/Jira/Webpage)
			v. timestamp
			vi. → Purpose: Improves filtering and accurate retrieval during search.
	5. Prepares final chunk objects for embedding
		a. After splitting, each chunk looks like:
		
		b. {
  "id": "doc12_chunk04",
  "text": "How to reset VPN password...",
  "metadata": { "source": "Wiki", "page": 2 }
}
		c. → Purpose: These chunks are now ready to be transformed into vectors.

Embedding Generator
(LLM Embedding Model → Vector Representation)
	• The Embedding Generator is the step in which we pass each chunk into an Embedding Model to convert text into semantic vectors.
	• The Embedding Generator takes each chunk of text and converts it into a numerical vector(mathematical representations)—a list of floating-point numbers.
	• These numbers represent the semantic meaning of the text.
	• These vectors (embeddings) allow the system to search by meaning, not by keywords.
	•  Traditional search (keyword search) fails when:
		• User does not use exact document words
	But embeddings solve this:
		• They convert text → meaning
		• The system retrieves documents that mean the same, even if words differ
	• Text embeddings
		• For normal text
	Code embeddings
		• Useful for GitHub/Jira queries
	Multi-modal embeddings
		• Images + text (CLIP etc.)
	
Vector Database (Storage Layer)
(Pinecone, Chroma, Weaviate, Milvus)
	• Once chunks are converted into embeddings (vectors), the vector database stores them in a way that allows extremely fast semantic similarity search(SSS).
	• A vector database is not like MongoDB or SQL.
	• Instead, it is specially designed to store high-dimensional vectors and retrieve the closest ones based on meaning.
	• Stores vectors + metadata
	For each chunk, the DB stores:
		• the vector (embeddings)
		• chunk text
		• source document
		• page number
		• tags / metadata (like Jira ticket, wiki page, version)
	Example entry:
	
	id: "policy_chunk_04"
vector: [0.221, -0.880, 0.112, ...]
metadata: {
  source: "Leave_Policy.pdf",
  page: 2,
  section: "Medical Leave",
  timestamp: 2024
}
	
	Indexing for ultra-fast search
		• Raw text → embeddings (by an embedding model)
		• Vector DB stores these vectors
		• HNSW happens after vector generation, not on raw text.
		• After vectors are stored → Vector DB builds the HNSW index
		• Only after vectors exist, HNSW can link similar vectors
		• Indexing is based on distance between vector embeddings
		• vector database uses HNSW to index and store them for fast semantic similarity search(SSS).
		• Vector DB uses specialized indexing algorithms like:
		• HNSW (Hierarchical Navigable Small World)
		• IVF-Faiss
		• Annoy
	These algorithms allow:
		• millisecond semantic search
		• even with millions of vectors
	Interview tip:
	👉 “HNSW is the most commonly used index for fast approximate nearest neighbor search.”
	
	Performs Similarity Search (Cosine / Dot Product)
	• We don’t manually compute cosine similarity or dot product. The vector database performs all similarity calculations internally. My job is only to generate embeddings and pass them to the vector DB. The DB handles indexing and fast retrieval using HNSW or IVF. This makes similarity search extremely fast and scalable.
	• results = vector_db.query(vector=query_embedding, top_k=5)
	When a user asks a question:
		• Convert the query to a vector
		• Compare it with stored vectors
		• Find the Top-K nearest chunks
		• Based on cosine similarity / dot product
		• Vector DB automatically Chooses cosine or dot product
	Example:
	User Query: “How do I apply for sick leave?”
	Vector DB returns chunks like:
		• “Employees can take medical leave…”
		• “Procedure for applying leave…”
	NOT:
		• “Password reset steps”
		• “Network configuration”
	
	Uses Metadata Filters (Very important)
	You can filter results by:
		• project name
		• year
		• department
		• document type
		• Jira issue type
	Example:
	
	Give me only Chunks:
Where project = "Project-X"
And category = "Security"
Limit 5
	This helps avoid irrelevant results.
	
	Sends Relevant Chunks to LLM
	After similarity search, the DB returns the most relevant chunks.
	These are added to the prompt context.
	Then the LLM uses this context to generate the final answer.
	This is how RAG prevents hallucination.
	EX -
	SYSTEM:
	You must answer using ONLY the information provided in context.  
	Do not guess.
	CONTEXT:
	Chunk 1:
	Employees are allowed 12 days of sick leave per calendar year.
	Chunk 2:
	Sick leave can be applied through the HR portal under Medical Leave.
	USER QUESTION:
	How many sick leaves do employees get?
	
User Query Input Layer
(User asks a question)

Query Embedding Generator
(Convert query into embedding vector)

def get_query_embedding(query):
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=query
    )

Vector Database Retrieval Layer
(Similarity Search + Metadata Filtering)
This layer is responsible for finding the most relevant chunks from the vector database using:
	1. Similarity Search → Uses cosine similarity / dot product
		• Cosine similarity: Measures the angle between vectors (how similar directions are).
		• Dot product: Measures the similarity based on vector magnitude and direction.
	2. Metadata Filtering → Filters using fields like:
		○ document_id
		○ created_date
		○ tags
		○ author
		○ page number
		○ category

Context Builder
(Top-K Relevant Chunks Merged)
After the Vector Database Retrieval Layer fetches the most relevant chunks, the Context Builder:
	1. Selects the Top-K chunks
		○ "K" is a number you define (e.g., top 5 chunks).
		○ These are the chunks that are most relevant to the user query based on similarity search and metadata filtering.
	2. Merges the chunks into a single context
		○ The goal is to create a coherent input for the LLM.
		○ This avoids overwhelming the model with too many separate chunks and ensures relevant information is consolidated.
Example:
Suppose the retrieved chunks for query "Tourist places in Kerala" are:
	• Chunk 1: "Kerala is known for its backwaters and houseboats."
	• Chunk 2: "Varkala beach is a popular tourist spot in Kerala."
	• Chunk 3: "Munnar is famous for tea plantations and hill stations."
If Top-2 (K=2) is chosen:
	• Selected chunks: Chunk 1 and Chunk 2
	• Merged context: "Kerala is known for its backwaters and houseboats. Varkala beach is a popular tourist spot in Kerala."
This merged context is then sent to the LLM to generate an answer to the user query.

LLM Reasoning Layer
(LLM generates grounded answer using context)

Final This layer is the part of a Retrieval-Augmented Generation (RAG) or AI system where the Large Language Model (LLM) processes the retrieved context and generates a final, grounded answer. Essentially, it’s where the “thinking” happens.
Inputs to this layer:
	1. User Query – The question or prompt provided by the user.
	2. Relevant Chunks / Context – Retrieved from the vector database after similarity search and metadata filtering. These are usually text segments from documents, FAQs, wikis, or other knowledge sources.
Process:
	1. Context Integration – The LLM takes the retrieved chunks and integrates them into its input prompt. This gives it the grounding to answer factually.
	2. Reasoning – The LLM processes both the user query and the provided context, performing:
		○ Comprehension: Understanding the question.
		○ Synthesis: Combining multiple chunks of information to form a coherent answer.
		○ Inference / Reasoning: Drawing conclusions, filling gaps, or explaining relationships.
	3. Answer Generation – The model outputs a response that is:
		○ Grounded in the context (citing sources or directly reflecting retrieved data)
		○ Coherent and natural language
Output Layer
(Display the final answer to the user)
<img width="1030" height="7088" alt="image" src="https://github.com/user-attachments/assets/bec00fd0-a779-40aa-9361-9c3cf9f09899" />
