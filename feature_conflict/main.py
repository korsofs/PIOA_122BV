def hello(name: str = "world") -> str:
    return f"Hello {name}."   # другое форматирование: без запятой и с точкой

if __name__ == "__main__":
    print("Running app...")
    print(hello())
