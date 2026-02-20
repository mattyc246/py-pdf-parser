import pymupdf
import requests
import os
import json

from ollama import chat
from ollama import ChatResponse


def extract_skills(text):
    response: ChatResponse = chat(
        model="gemma3",
        messages=[
            {
                "role": "user",
                "content": """Extract information from this resume and structure it as JSON with the following format:
{
  "name": "",
  "tags": [],
  "experience": [
    {
      "title": "",
      "company": "",
      "dates": "",
      "responsibilities": []
    }
  ],
  "skills": [],
  "education": [
    {
      "degree": "",
      "university": "",
      "graduation_date": ""
    }
  ],
  "languages": [
    {
      "language": "",
      "proficiency": ""
    }
  ],
  "references": [
    {
      "name": "",
      "title": "",
      "company": "",
      "contact": "",
      "email": ""
    }
  ]
}

For the "tags" field, extract key words and phrases that represent important skills, job titles, industries, or areas of expertise mentioned in the resume.

Resume text:
"""
                + text,
            },
        ],
    )

    print(response.message.content)


def main():
    resume_urls = []
    resume_url = None
    # Open resumes.json file and read the list of resume URLs
    with open("resumes.json", "r") as f:
        resume_urls = json.load(f)
        # Just take the first one for now
        resume_url = resume_urls[0]
    # Download the resume PDF from the URL
    response = requests.get(resume_url)
    # Save the PDF to a temporary file
    with open("temp_resume.pdf", "wb") as f:
        f.write(response.content)
    # Open the PDF file using PyMuPDF
    doc = pymupdf.open("temp_resume.pdf")
    # Extract text from the PDF
    text = ""
    for page in doc:
        text += page.get_text()
    # Print the extracted text
    extract_skills(text)
    # Close the PDF document
    doc.close()
    # Delete the temporary PDF file
    os.remove("temp_resume.pdf")


if __name__ == "__main__":
    main()
