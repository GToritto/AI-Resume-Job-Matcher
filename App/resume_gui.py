import os
import re
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
import webbrowser
from threading import Thread
import csv
from collections import Counter

from pdfminer.high_level import extract_text as extract_pdf_text
from docx import Document
import requests
from bs4 import BeautifulSoup
from sentence_transformers import SentenceTransformer, util

def extract_text(file_path):
    if file_path.endswith('.pdf'):
        return extract_pdf_text(file_path)
    elif file_path.endswith('.docx'):
        doc = Document(file_path)
        return "\n".join([para.text for para in doc.paragraphs])
    else:
        raise ValueError("Unsupported file type. Use PDF or DOCX.")

def scrape_remoteok():
    url = "https://remoteok.com/remote-dev-jobs"
    headers = {'User-Agent': 'Mozilla/5.0'}
    resp = requests.get(url, headers=headers)
    soup = BeautifulSoup(resp.text, 'html.parser')

    job_data = []
    jobs = soup.find_all('tr', class_='job')
    for job in jobs:
        title = job.find('h2')
        if not title:
            continue
        title = title.text.strip()

        link = job.get('data-href')
        if not link:
            continue
        link = f"https://remoteok.com{link}"

        description = job.text.strip()
        job_data.append({
            'title': title,
            'link': link,
            'description': description
        })

    return job_data

class ResumeMatcherGUI:
    def __init__(self, root):
        ctk.set_appearance_mode("System") 
        ctk.set_default_color_theme("blue")

        self.root = root
        self.root.title("AI Resume Job Matcher")
        self.root.geometry("750x650")

        self.file_path = tk.StringVar()
        self.threshold = tk.DoubleVar(value=70.0)
        self.matches = []

        # Frame wrapper
        self.frame = ctk.CTkFrame(root)
        self.frame.pack(padx=20, pady=20, expand=True, fill="both")

        self.label_resume = ctk.CTkLabel(self.frame, text="Resume Path:")
        self.label_resume.grid(row=0, column=0, columnspan=2, pady=(10, 5))

        self.entry_resume = ctk.CTkEntry(self.frame, textvariable=self.file_path, width=400)
        self.entry_resume.grid(row=1, column=0, columnspan=2, pady=5)

        self.button_browse = ctk.CTkButton(self.frame, text="Browse", command=self.browse_file)
        self.button_browse.grid(row=2, column=0, columnspan=2, pady=(0, 10))

        # Slider
        self.label_slider = ctk.CTkLabel(self.frame, text="Match Threshold (%)")
        self.label_slider.grid(row=3, column=0, columnspan=2, pady=(20, 5))

        self.slider = ctk.CTkSlider(self.frame, from_=0, to=100, variable=self.threshold, width=400, command=self.update_threshold_label)
        self.slider.grid(row=4, column=0, columnspan=2, pady=5)

        self.label_threshold_value = ctk.CTkLabel(self.frame, text=f"{int(self.threshold.get())}%")
        self.label_threshold_value.grid(row=5, column=0, columnspan=2)

        # Buttons
        self.button_match = ctk.CTkButton(self.frame, text="Find Matching Jobs", command=self.start_matching)
        self.button_match.grid(row=6, column=0, columnspan=2, pady=(10, 5))

        self.button_export = ctk.CTkButton(self.frame, text="Export to CSV", command=self.export_to_csv)
        self.button_export.grid(row=7, column=0, columnspan=2, pady=5)

        self.theme_toggle = ctk.CTkSwitch(self.frame, text="Dark Mode", command=self.toggle_theme)
        self.theme_toggle.select()
        self.theme_toggle.grid(row=0, column=1, sticky="e", padx=(0, 10), pady=(10, 0))


        # Results area
        self.result_box = ctk.CTkTextbox(self.frame, wrap='word', width=680, height=250)
        self.result_box.grid(row=9, column=0, columnspan=2, padx=10, pady=10)
        self.result_box.bind("<Button-1>", self.handle_link_click)

        # Grid config
        self.frame.grid_columnconfigure(0, weight=1)
        self.frame.grid_columnconfigure(1, weight=0)

    def update_threshold_label(self, value):
        self.label_threshold_value.configure(text=f"{int(float(value))}%")

    def browse_file(self):
        path = filedialog.askopenfilename(filetypes=[("Resumes", "*.pdf *.docx")])
        if path:
            self.file_path.set(path)

    def start_matching(self):
        self.result_box.delete('1.0', 'end')
        path = self.file_path.get()
        if not os.path.isfile(path):
            messagebox.showerror("Error", "Please select a valid resume file.")
            return

        self.result_box.insert('end', "Processing...\n")
        Thread(target=self.match_jobs_thread, args=(path,)).start()

    def match_jobs_thread(self, path):
        try:
            resume_text = extract_text(path)
            jobs = scrape_remoteok()

            model = SentenceTransformer('all-MiniLM-L6-v2')
            resume_embedding = model.encode(resume_text, convert_to_tensor=True)
            job_embeddings = model.encode([job['description'] for job in jobs], convert_to_tensor=True)
            similarities = util.pytorch_cos_sim(resume_embedding, job_embeddings)[0]

            threshold_val = self.threshold.get() / 100.0
            self.matches = [
                {**jobs[i], "score": round(similarities[i].item(), 2)}
                for i in range(len(jobs))
                if similarities[i].item() >= threshold_val
            ]

            self.result_box.delete('1.0', 'end')
            if not self.matches:
                self.result_box.insert('end', "No jobs matched your threshold.\n")
            else:
                for job in self.matches:
                    self.result_box.insert('end', f"{job['title']} ({int(job['score'] * 100)}%)\n{job['link']}\n\n")
        except Exception as e:
            self.result_box.insert('end', f"Error: {str(e)}\n")

    def handle_link_click(self, event):
        idx = self.result_box.index(f"@{event.x},{event.y}")
        line = self.result_box.get(idx + " linestart", idx + " lineend")
        if line.startswith("http"):
            webbrowser.open(line)

    def export_to_csv(self):
        if not self.matches:
            messagebox.showinfo("Export", "No matches to export.")
            return

        save_path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
        if save_path:
            with open(save_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=["title", "link", "score"])
                writer.writeheader()
                for job in self.matches:
                    writer.writerow({
                        "title": job['title'],
                        "link": job['link'],
                        "score": job['score']
                    })
            messagebox.showinfo("Export", f"Exported {len(self.matches)} jobs to CSV.")

    def toggle_theme(self):
        mode = "Dark" if self.theme_toggle.get() else "Light"
        ctk.set_appearance_mode(mode)

if __name__ == "__main__":
    root = ctk.CTk()
    app = ResumeMatcherGUI(root)
    root.mainloop()
