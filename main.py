import os
import logging
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
import streamlit as st

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

# Set the DeepInfra API key from environment variables
deep_infra_api_key = os.getenv("DEEP_INFRA_API_KEY", "VxCqTQoMdguLd8Tp6m3U4CcFz7Jc3bZ0")
base_url = "https://api.deepinfra.com/v1/openai"

# Function to extract text from uploaded document (PDF)
def extract_text_from_pdf(pdf_file: bytes) -> str:
    logger.info("Starting PDF text extraction")
    try:
        doc = fitz.open(stream=pdf_file, filetype="pdf")
        text = "".join([page.get_text("text") for page in doc])
        logger.info("Successfully extracted text from the PDF")
        return text
    except Exception as e:
        logger.error(f"Error during PDF text extraction: {e}")
        st.error(f"PDF extraction failed: {str(e)}")
        return ""

# Function to generate lesson plan using DeepInfra model
def generate_lesson_plan(extracted_text: str) -> str:
    logger.info("Starting lesson plan generation with DeepInfra")
    prompt = f"""
    Based on the following textbook chapter content:

{extracted_text}

Please generate a comprehensive lesson plan for teachers, structured into three distinct sections:

Introduction: Chapter name and Create an engaging introduction that captures students' attention and effectively introduces the key concepts of the chapter.
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
    """
    
    response = requests.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {deep_infra_api_key}"},
        json={"model": "meta-llama/Meta-Llama-3-70B-Instruct", "messages": [{"role": "user", "content": prompt}], "max_tokens": 10000}
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

# Function to create the PDF with proper formatting
from reportlab.platypus import ListFlowable, ListItem
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
    bullet_style = styles['Bullet']
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
            
            # Add heading to story with heading style (bold)
            story.append(Paragraph(f"<b>{heading.strip()}:</b>", heading_style))
            story.append(Spacer(1, 12))  # Add a small space after each heading
            
            # Check for bullet points and format appropriately
            if "\n" in content.strip():
                # If content contains line breaks, convert them into bullet points
                bullet_points = content.strip().split("\n")
                bullet_items = [ListItem(Paragraph(point.strip(), bullet_style)) for point in bullet_points]
                story.append(ListFlowable(bullet_items, bulletType='bullet'))
            else:
                # Add body text to story with body text style for paragraphs
                story.append(Paragraph(content.strip(), body_style))
            
            story.append(Spacer(1, 12))  # Add a small space after each section of text
            
            # Generate and add image based on the content (optional for visualization)
            image_buffer = generate_image_from_text(content.strip())
            img = ReportLabImage(image_buffer, width=8 * inch, height=3 * inch)
            img.hAlign = 'CENTER'  # Center align the image
            story.append(img)
            story.append(Spacer(1, 24))  # Add space after the image
    
    # Build the PDF document
    doc.build(story)
    
    # Move buffer pointer to start so it can be returned as a response
    buffer.seek(0)
    
    logger.info("PDF document created successfully")
    return buffer

# Streamlit app
st.sidebar.title("Project Overview")
st.sidebar.write("""
### AI Lesson Plan Generator

This tool takes a PDF document, extracts its content, and generates a comprehensive lesson plan for teachers, including an introduction, main body, and class activity.

#### Tech Stack:
- **Language Model**: Meta-LLaMA-3-70B-Instruct (via DeepInfra)
- **PDF Processing**: PyMuPDF (fitz)
- **PDF Generation**: ReportLab
- **Image Generation**: DeepInfra API (FLUX-1-schnell)
- **UI**: Streamlit
""")

st.sidebar.write("### Author")
st.sidebar.write("Mayank Chaudhry")

st.title("AI Lesson Plan Generator")
st.write("Upload a PDF, and we'll generate a detailed lesson plan based on the content!")

# File upload functionality
uploaded_file = st.file_uploader("Choose a PDF file", type=["pdf"])

if uploaded_file is not None:
    try:
        # Read file and extract text
        file_bytes = uploaded_file.read()
        extracted_text = extract_text_from_pdf(file_bytes)
        
        if extracted_text:
            # Generate lesson plan
            lesson_plan = generate_lesson_plan(extracted_text)
            st.text_area("Generated Lesson Plan", lesson_plan, height=400)

            # Generate and download the PDF
            if st.button("Download Lesson Plan as PDF"):
                pdf_buffer = create_pdf(lesson_plan)
                st.download_button(
                    label="Download PDF",
                    data=pdf_buffer,
                    file_name="lesson_plan.pdf",
                    mime="application/pdf"
                )
    except Exception as e:
        st.error(f"An error occurred: {str(e)}")
