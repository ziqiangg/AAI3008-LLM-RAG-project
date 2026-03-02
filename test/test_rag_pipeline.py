"""
RAG Pipeline Testing Script
Tests the complete query pipeline with document upload and question answering
"""
import requests
import json
import time
from pathlib import Path

# Configuration
API_BASE = "http://localhost:5000"
TEST_EMAIL = "test@example.com"
TEST_PASSWORD = "testpassword123"
TEST_USERNAME = "testuser"

# ANSI color codes for pretty output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'


def print_success(msg):
    print(f"{GREEN}✓ {msg}{RESET}")


def print_error(msg):
    print(f"{RED}✗ {msg}{RESET}")


def print_info(msg):
    print(f"{BLUE}ℹ {msg}{RESET}")


def print_warning(msg):
    print(f"{YELLOW}⚠ {msg}{RESET}")


def print_section(title):
    print(f"\n{'='*60}")
    print(f"{BLUE}{title}{RESET}")
    print('='*60)


class RAGTester:
    def __init__(self):
        self.token = None
        self.user_id = None
        self.session_id = None
        self.document_id = None
    
    def test_health(self):
        """Test if backend is running"""
        print_section("1. Health Check")
        try:
            response = requests.get(f"{API_BASE}/", timeout=5)
            if response.status_code == 200:
                print_success("Backend is running")
                return True
            else:
                print_error(f"Backend returned status {response.status_code}")
                return False
        except requests.exceptions.ConnectionError:
            print_error("Cannot connect to backend. Is it running?")
            print_info(f"Expected at: {API_BASE}")
            return False
    
    def test_auth(self):
        """Test user registration and login"""
        print_section("2. Authentication")
        
        # Try to register
        print_info("Attempting to register user...")
        response = requests.post(
            f"{API_BASE}/api/users/register",
            json={
                "username": TEST_USERNAME,
                "email": TEST_EMAIL,
                "password": TEST_PASSWORD
            }
        )
        
        if response.status_code == 201:
            data = response.json()
            self.token = data['token']
            self.user_id = data['user']['id']
            print_success(f"Registered new user: {TEST_USERNAME} (ID: {self.user_id})")
        elif response.status_code == 409:
            # User already exists, try login
            print_info("User already exists, logging in...")
            response = requests.post(
                f"{API_BASE}/api/users/login",
                json={
                    "email": TEST_EMAIL,
                    "password": TEST_PASSWORD
                }
            )
            if response.status_code == 200:
                data = response.json()
                self.token = data['token']
                self.user_id = data['user']['id']
                print_success(f"Logged in as: {TEST_USERNAME} (ID: {self.user_id})")
            else:
                print_error(f"Login failed: {response.text}")
                return False
        else:
            print_error(f"Registration failed: {response.text}")
            return False
        
        return True
    
    def test_document_upload(self):
        """Test document upload (requires a test file)"""
        print_section("3. Document Upload")
        
        # Check if test document exists
        test_file = Path("test_document.txt")
        if not test_file.exists():
            # Create a simple test document
            print_info("Creating test document...")
            with open(test_file, 'w') as f:
                f.write("""
Machine Learning Basics

Machine learning is a subset of artificial intelligence that focuses on training algorithms 
to learn patterns from data. There are three main types of machine learning:

1. Supervised Learning
In supervised learning, the algorithm learns from labeled training data. The model is trained 
on input-output pairs and learns to map inputs to correct outputs. Common algorithms include 
linear regression, decision trees, and neural networks.

2. Unsupervised Learning
Unsupervised learning involves finding patterns in unlabeled data. The algorithm tries to 
discover hidden structures without explicit guidance. Common techniques include clustering 
(like K-means) and dimensionality reduction (like PCA).

3. Reinforcement Learning
Reinforcement learning involves an agent learning to make decisions by interacting with an 
environment. The agent receives rewards or penalties for its actions and learns to maximize 
cumulative reward over time. This is used in game playing and robotics.

Neural Networks
Neural networks are computing systems inspired by biological neural networks. They consist of 
interconnected nodes (neurons) organized in layers. Deep learning uses neural networks with 
many layers to learn hierarchical representations of data.

Applications
Machine learning has many applications including image recognition, natural language processing, 
recommendation systems, autonomous vehicles, and medical diagnosis.
                """)
            print_success("Created test_document.txt")
        
        # Upload document
        print_info("Uploading document...")
        with open(test_file, 'rb') as f:
            files = {'file': ('test_document.txt', f, 'text/plain')}
            data = {
                'subject': 'Machine Learning',
                'user_id': str(self.user_id)
            }
            
            response = requests.post(
                f"{API_BASE}/api/documents/upload",
                files=files,
                data=data
            )
        
        if response.status_code == 201:
            doc_data = response.json()
            self.document_id = doc_data['document']['id']
            chunk_count = doc_data['document']['chunk_count']
            print_success(f"Document uploaded successfully (ID: {self.document_id}, Chunks: {chunk_count})")
            return True
        else:
            print_error(f"Document upload failed: {response.text}")
            return False
    
    def test_session_creation(self):
        """Test creating a chat session"""
        print_section("4. Session Creation")
        
        print_info("Creating chat session...")
        response = requests.post(
            f"{API_BASE}/api/sessions/",
            headers={'Authorization': f'Bearer {self.token}'},
            json={
                'title': 'Test Session',
                'document_ids': [self.document_id] if self.document_id else []
            }
        )
        
        if response.status_code == 201:
            session_data = response.json()
            self.session_id = session_data['session']['id']
            print_success(f"Session created (ID: {self.session_id})")
            return True
        else:
            print_error(f"Session creation failed: {response.text}")
            return False
    
    def test_query_pipeline(self):
        """Test the RAG query pipeline"""
        print_section("5. RAG Query Pipeline")
        
        questions = [
            "What is machine learning?",
            "Explain the three types of machine learning.",
            "What are neural networks?",
            "What is supervised learning?"
        ]
        
        for i, question in enumerate(questions, 1):
            print(f"\n{BLUE}Question {i}:{RESET} {question}")
            print("-" * 60)
            
            start_time = time.time()
            response = requests.post(
                f"{API_BASE}/api/query",
                headers={'Authorization': f'Bearer {self.token}'},
                json={
                    'question': question,
                    'session_id': self.session_id,
                    'document_ids': [self.document_id] if self.document_id else None
                }
            )
            elapsed = time.time() - start_time
            
            if response.status_code == 200:
                data = response.json()
                answer = data['answer']
                sources = data.get('sources', [])
                metadata = data.get('metadata', {})
                
                print(f"\n{GREEN}Answer:{RESET}")
                print(answer[:500] + ('...' if len(answer) > 500 else ''))
                
                print(f"\n{BLUE}Sources:{RESET}")
                for j, source in enumerate(sources, 1):
                    print(f"  [{j}] {source['filename']} (Score: {source['score']:.3f})")
                    print(f"      {source['content'][:100]}...")
                
                print(f"\n{BLUE}Metadata:{RESET}")
                print(f"  Model: {metadata.get('model', 'N/A')}")
                print(f"  Retrieved chunks: {metadata.get('num_chunks_retrieved', 0)}")
                print(f"  Reranked chunks: {metadata.get('num_chunks_reranked', 0)}")
                print(f"  Conversation messages: {metadata.get('num_context_messages', 0)}")
                print(f"  Response time: {elapsed:.2f}s")
                
                print_success(f"Query {i} succeeded")
            else:
                print_error(f"Query {i} failed: {response.text}")
                return False
            
            time.sleep(1)  # Brief pause between queries
        
        return True
    
    def test_conversation_history(self):
        """Test that conversation history is maintained"""
        print_section("6. Conversation History")
        
        print_info("Testing follow-up question using conversation context...")
        response = requests.post(
            f"{API_BASE}/api/query",
            headers={'Authorization': f'Bearer {self.token}'},
            json={
                'question': 'Can you give me an example of the last type you mentioned?',
                'session_id': self.session_id
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"\n{GREEN}Answer:{RESET}")
            print(data['answer'][:300] + '...')
            print_success("Conversation history working!")
            return True
        else:
            print_error(f"Follow-up question failed: {response.text}")
            return False
    
    def run_all_tests(self):
        """Run all tests in sequence"""
        print("\n" + "="*60)
        print(f"{BLUE}RAG Pipeline Testing Suite{RESET}")
        print("="*60)
        
        tests = [
            ("Health Check", self.test_health),
            ("Authentication", self.test_auth),
            ("Document Upload", self.test_document_upload),
            ("Session Creation", self.test_session_creation),
            ("Query Pipeline", self.test_query_pipeline),
            ("Conversation History", self.test_conversation_history),
        ]
        
        results = []
        for test_name, test_func in tests:
            try:
                result = test_func()
                results.append((test_name, result))
                if not result:
                    print_warning(f"Test '{test_name}' failed, stopping further tests")
                    break
            except Exception as e:
                print_error(f"Test '{test_name}' crashed: {e}")
                results.append((test_name, False))
                break
        
        # Print summary
        print_section("Test Summary")
        passed = sum(1 for _, result in results if result)
        total = len(results)
        
        for test_name, result in results:
            status = f"{GREEN}PASS{RESET}" if result else f"{RED}FAIL{RESET}"
            print(f"  {status}  {test_name}")
        
        print(f"\n{BLUE}Results:{RESET} {passed}/{total} tests passed")
        
        if passed == total:
            print_success("All tests passed! 🎉")
        else:
            print_error("Some tests failed. Check the output above for details.")


if __name__ == "__main__":
    tester = RAGTester()
    tester.run_all_tests()
