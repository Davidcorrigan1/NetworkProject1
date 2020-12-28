import firebase_admin
from firebase_admin import credentials, firestore, storage, db
import os

cred=credentials.Certificate('./serviceAccountKey.json')


firebase_admin.initialize_app(cred, {
    'storageBucket': 'sensepi-27797.appspot.com',
    'databaseURL': 'https://sensepi-27797.firebaseio.com/'
})

bucket = storage.bucket()

ref = db.reference('/')
home_ref = ref.child('file')

def store_file(fileLoc):

    filename=os.path.basename(fileLoc)

    # Store File in FB Bucket
    blob = bucket.blob(filename)
    outfile=fileLoc
    blob.upload_from_filename(outfile)
    blob.make_public()
    print("URL: ", blob.public_url)
    return(blob.public_url)

def push_db(fileLoc, time, childInRoom, adultInRoom):

    filename=os.path.basename(fileLoc)

    # Push file reference to image in Realtime DB
    home_ref.push({
        'image': filename,
        'timestamp': time,
        'childPresent': childInRoom,
        'adultPresent': adultInRoom}
    )


if __name__ == "__main__":
    f = open("./test.txt", "w")
    f.write("a demo upload file to test Firebase Storage")
    f.close()
    store_file('./test.txt')
    push_db('./test.txt', '12/11/2020 9:00', True, False )


