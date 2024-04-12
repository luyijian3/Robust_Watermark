import base64
from PIL import Image
def load_image_local(file_path):
    image = Image.open(file_path)
    return image
    #with open(file_path, "rb") as img_file:
    #    base64_data = base64.b64encode(img_file.read()).decode('utf-8')
    #    uri=f"data:image/png;base64,{base64_data}"