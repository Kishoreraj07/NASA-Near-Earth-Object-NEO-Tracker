# 🚀 NASA Near-Earth Object (NEO) Tracker

This is a Streamlit-based web application that tracks Near-Earth Objects using NASA's public API. It collects and stores asteroid data, analyzes potential hazards, and visualizes key metrics such as asteroid size, approach speed, and distance.

## 🌐 Live Demo
You can run this app locally using Streamlit. See below for instructions.

## 📦 Features

- Pulls NEO data from NASA's API for a customizable date range
- Stores data in a local SQLite database
- Displays statistics about:
  - Potentially hazardous asteroids
  - Relative velocity and distance
  - Estimated asteroid size
- Visualization using Seaborn and Matplotlib
- Progress indicators for data fetching

## 🛠 Technologies Used

- Python
- Streamlit
- SQLite
- Requests
- Matplotlib
- Seaborn
- Pandas

## 🚀 Getting Started

### 1. Clone the repository
```bash
git clone https://github.com/your-username/nasa-neo-tracker.git
cd nasa-neo-tracker
