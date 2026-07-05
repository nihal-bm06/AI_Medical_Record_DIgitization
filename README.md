# AI_Medical_Record_DIgitization
An AI-powered medical record digitization system that transforms unstructured clinical digital documents into structured, machine-learning-ready datasets using Large Language Models (LLMs), and rule-based validation.

The application processes multiple patient records, extracts clinically relevant information, and exports the results in CSV, Excel, and JSON formats through an intuitive web interface.

🚀 Features

📄 Upload ZIP folders containing multiple patient records
🤖 LLM-powered structured medical information extraction
✅ Rule-based validation for improved data consistency
📊 Automatic export to CSV, Excel, and JSON
🌐 User-friendly Flask web interface
⚡ Batch processing of multiple patient records
🔄 Prompt caching for efficient processing

🛠️ Tech Stack

Backend: Flask (Python)
AI: Large Language Models (Gemini/OpenRouter), Prompt Engineering
Data Processing: Pandas, Rule-based NLP
Output Formats: CSV, Excel, JSON
Frontend: HTML, CSS, JavaScript

📂 Workflow

Upload a ZIP file containing patient records.
Extract and organize patient folders.
Use an LLM to extract structured clinical information.
Validate and standardize extracted fields.
Export the processed data as CSV, Excel, and JSON.

🎯 Objective

Healthcare institutions often maintain patient information in handwritten or semi-structured records, making large-scale analysis difficult.

This project automates the digitization process by converting unstructured medical records into structured datasets that can be used for:

Clinical research
Machine Learning
Disease prediction
Hospital data management
Healthcare analytics

📊 Output

The system generates structured patient information including demographic details, clinical findings, diagnoses, medical history, and other relevant attributes in machine-learning-ready formats.

Supported exports:

✅ CSV
✅ Excel (.xlsx)
✅ JSON

▶️ Getting Started

Clone the repository
git clone https://github.com/nihal-bm06/AI_Medical_Record_DIgitization.git
cd AI_Medical_Record_DIgitization
Install dependencies
pip install -r requirements.txt
Run the application
python app.py

Open your browser and visit:

http://localhost:5000

📈 Future Improvements

Integration with Electronic Health Record (EHR) systems
Support for making a custom OCR engine as open source OCR engines doesn't accurately convert it into proper digital text.
Improved medical entity recognition
Real-time processing pipeline
Secure authentication and user management
Docker deployment
Cloud-based scalability

👨‍💻 Author

Nihal B M

B.Tech Computer Science & Engineering (AI & ML)
Manipal Institute of Technology

📄 License

This project is intended for educational and research purposes.
