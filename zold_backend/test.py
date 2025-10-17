from fastapi import FastAPI

app = FastAPI()

items = []

@app.get("/")
# rout = different urls 
def root():
    return {"message", "World"}

@app.post("/items")
def create_item(item: str):
    items.append(item)
    return items

@app.get("/items{item_id}")
def get_item(item: int) :
    items.append(item)
    return items
