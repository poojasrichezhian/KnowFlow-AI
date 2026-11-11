"""Text extraction for uploaded files."""
import io


def extract(filename, data):
    """Returns (kind, text). kind is 'tasks' for CSV task exports, otherwise 'document'."""
    name = filename.lower()
    if name.endswith(".pdf"):
        import pymupdf
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            return "document", "\n".join(page.get_text() for page in doc)
    if name.endswith(".docx"):
        import docx
        d = docx.Document(io.BytesIO(data))
        return "document", "\n".join(p.text for p in d.paragraphs)
    if name.endswith(".csv"):
        return "tasks", data.decode("utf-8-sig", errors="replace")
    if name.endswith((".md", ".txt", ".rst")):
        return "document", data.decode("utf-8", errors="replace")
    raise ValueError("Upload a PDF, DOCX, Markdown, text or CSV file.")
