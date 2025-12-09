from mongoengine import connect, Document, StringField

connect(
    host="mongodb+srv://your_username:your_password@cluster0.sb7z5xv.mongodb.net/library?retryWrites=true&w=majority",
    alias="default"
)

class Test(Document):
    name = StringField()

t = Test(name="hello atlas")
t.save()

print("Saved:", t.id)
