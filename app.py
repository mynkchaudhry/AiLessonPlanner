import os
import logging
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import StreamingResponse
from io import BytesIO
import requests
import base64
import fitz  # PyMuPDF
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as ReportLabImage
from reportlab.lib import colors
from PIL import Image as PILImage
from reportlab.lib.units import inch 
from fastapi.middleware.cors import CORSMiddleware



# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

file_handler = logging.FileHandler('lesson_plan_generator.log')
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

# Get the root logger and attach handlers
logger = logging.getLogger()
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Initialize FastAPI app
app = FastAPI()
# Allow CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5500"],  # Replace "*" with your frontend's URL in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Set the DeepInfra API key from environment variables
deep_infra_api_key = os.getenv("DEEP_INFRA_API_KEY", "VxCqTQoMdguLd8Tp6m3U4CcFz7Jc3bZ0")
base_url = "https://api.deepinfra.com/v1/openai"

# Function to extract text from uploaded PDF file
def extract_text_from_pdf(pdf_file: bytes) -> str:
    logger.info("Starting PDF text extraction")
    try:
        doc = fitz.open(stream=pdf_file, filetype="pdf")
        text = "".join([page.get_text("text") for page in doc])
        logger.info("Successfully extracted text from the PDF")
        return text
    except Exception as e:
        logger.error(f"Error during PDF text extraction: {e}")
        raise HTTPException(status_code=500, detail=f"PDF extraction failed: {str(e)}")

# Function to generate lesson plan using DeepInfra model
def generate_lesson_plan(extracted_text: str) -> str:
    logger.info("Starting lesson plan generation with DeepInfra")
    prompt = f"""
        
Based on the following textbook chapter content:

{extracted_text}

Please generate a comprehensive lesson plan for teachers, structured into three distinct sections:

Introduction: Create an engaging introduction that captures students' attention and effectively introduces the key concepts of the chapter.
Output Format:
Paragraph: Start with a brief introduction to the key concept(s) of the chapter.
Key Question: Pose an open-ended question to engage students and spark curiosity.
Transition: Summarize the introduction and link it to the main body of the lesson.

Main Body: Present the core lesson material in a clear and organized manner. Focus on detailed explanations and relevant real-world examples that facilitate student understanding of the chapter's content. Ensure the material is logically sequenced.
Output Format:
Paragraph: Provide a detailed explanation of the key concept(s).
Bullet Points: List the critical components, definitions, or facts.
Detailed Explanation: Describe the process or concept step-by-step.
Transition: Conclude the main body and prepare the students for the class activity.

Class Activity: Design an interactive class activity that reinforces the lesson objectives and promotes active participation. The activity should seamlessly connect back to both the introduction and the main body of the lesson.
Output Format:

Activity Name: Provide a creative name for the activity.
Bullet Points: Describe the steps or materials required for the activity.
Objective: Explain how the activity supports learning and connects to the chapter’s content.
Debrief: Summarize the activity and link it back to the key concepts learned in the lesson.
Additionally, ensure that each section is well-structured and maintains contextual alignment with the others. For example, if I choose to regenerate the main body, it should not disrupt the coherence of the introduction and class activity. Similarly, any updates to the class activity should remain consistent with the themes presented in the other two sections.
    3. Class Activity: Design an interactive class activity that reinforces the lesson objectives and promotes active participation.
    """
    response = requests.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {deep_infra_api_key}"},
        json={"model": "meta-llama/Meta-Llama-3-70B-Instruct", "messages": [{"role": "user", "content": prompt}], "max_tokens": 1000}
    )
    response.raise_for_status()
    lesson_plan = response.json()['choices'][0]['message']['content'].strip()
    logger.info("Lesson plan successfully generated")
    return lesson_plan

# Function to generate images based on the lesson plan content
def generate_image_from_text(text: str) -> BytesIO:
    logger.info("Starting image generation")
    url = "https://api.deepinfra.com/v1/inference/black-forest-labs/FLUX-1-schnell"
    payload = {"prompt": text}
    headers = {"Authorization": f"Bearer {deep_infra_api_key}"}
    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    image_data_base64 = response.json()['images'][0].split(",")[1]
    image_data = base64.b64decode(image_data_base64)
    image = PILImage.open(BytesIO(image_data))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    logger.info("Image successfully generated")
    return buffer

# Function to create the PDF
def create_pdf(lesson_plan: str) -> BytesIO:
    logger.info("Creating PDF document")
    
    # Buffer to store PDF in memory
    buffer = BytesIO()
    
    # Create a SimpleDocTemplate object
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=18)
    
    # Get sample style sheet and define custom styles
    styles = getSampleStyleSheet()
    title_style = styles['Title']
    heading_style = styles['Heading2']
    body_style = styles['BodyText']
    
    # Custom ParagraphStyle for better spacing and alignment
    body_style.alignment = 4  # Justify the text
    body_style.leading = 14    # Line spacing
    heading_style.alignment = 1  # Center the headings
    
    # List to store flowable elements for the PDF document
    story = []
    
    # Add a title to the document
    story.append(Paragraph("Lesson Plan", title_style))
    story.append(Spacer(1, 24))  # Add space after the title
    
    # Split the lesson plan into sections based on the newlines
    sections = lesson_plan.split("\n\n")
    
    for section in sections:
        if ':' in section:
            # Separate heading and content
            heading, content = section.split(":", 1)
            
            # Add heading to story with heading style
            story.append(Paragraph(heading.strip() + ":", heading_style))
            story.append(Spacer(1, 12))  # Add a small space after each heading
            
            # Add body text to story with body text style
            story.append(Paragraph(content.strip(), body_style))
            story.append(Spacer(1, 12))  # Add a small space after each section of text
            
            # Generate and add image based on the content
            image_buffer = generate_image_from_text(content.strip())
            img = ReportLabImage(image_buffer, width=4 * inch, height=3 * inch)
            img.hAlign = 'CENTER'  # Center align the image
            story.append(img)
            story.append(Spacer(1, 24))  # Add space after the image
    
    # Build the PDF document
    doc.build(story)
    
    # Move buffer pointer to start so it can be returned as a response
    buffer.seek(0)
    
    logger.info("PDF document created successfully")
    return buffer


# FastAPI route to upload PDF and generate lesson plan
@app.post("/generate-lesson-plan/")
async def upload_and_generate_plan(file: UploadFile = File(...)):
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed.")
    pdf_bytes = await file.read()
    extracted_text = extract_text_from_pdf(pdf_bytes)
    lesson_plan = generate_lesson_plan(extracted_text)
    pdf_buffer = create_pdf(lesson_plan)
    return StreamingResponse(pdf_buffer, media_type='application/pdf', headers={"Content-Disposition": "attachment; filename=lesson_plan.pdf"})
