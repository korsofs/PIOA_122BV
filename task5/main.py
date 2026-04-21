def hello(name="world"):
    if not name:
        name = "world"
    return f"Hello, {name}!"

if __name__ == "__main__":
    print(hello())
