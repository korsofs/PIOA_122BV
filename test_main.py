from main import hello
from main import goodbye

def test_hello():
    assert hello("Git") == "Hello, Git!"

def test_goodbye():
    assert goodbye("Git") == "Goodbye, Git."
