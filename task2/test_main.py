from main import hello

def test_hello_custom():
    assert hello("Git") == "Hello, Git!"

def test_hello_default():
    assert hello() == "Hello, world!"