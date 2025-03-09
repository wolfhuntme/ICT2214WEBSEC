import firebase_admin
from firebase_admin import credentials, firestore

class FirestoreDB:
    def __init__(self):
        """Initialize Firestore connection, avoiding duplicate initialization."""
        if not firebase_admin._apps:
            cred = credentials.Certificate("we66y-3e209-firebase-adminsdk-fbsvc-b3f5b3fde2.json")  # Replace with your Firestore key
            firebase_admin.initialize_app(cred)
        self.db = firestore.client()

    def add_document(self, collection, doc_id, data):
        """Add or update a document in Firestore."""
        doc_ref = self.db.collection(collection).document(doc_id)
        doc_ref.set(data, merge=True)  # Merge updates to avoid overwriting
        print(f"[+] Updated Firestore: {collection}/{doc_id}")

    def get_document(self, collection, doc_id):
        """Retrieve a document from Firestore."""
        doc = self.db.collection(collection).document(doc_id).get()
        return doc.to_dict() if doc.exists else None

    def delete_document(self, collection, doc_id):
        """Delete a document from Firestore."""
        self.db.collection(collection).document(doc_id).delete()
        print(f"[-] Deleted Firestore: {collection}/{doc_id}")

    def get_all_documents(self, collection):
        """Retrieve all documents in a collection."""
        docs = self.db.collection(collection).stream()
        return {doc.id: doc.to_dict() for doc in docs}

if __name__ == "__main__":
    db = FirestoreDB()
    db.add_document("test_collection", "test_doc", {"message": "Hello, Firestore!"})
    print(db.get_all_documents("test_collection"))
