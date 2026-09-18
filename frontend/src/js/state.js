/** Intake state and question banks. Persistence is handled by the authenticated API. */
let state = {
  view: "intake",
  step: 0,
  q: 0,
  answers: [],
  choice: "",
  name: "",
  age: "",
  sex: "Prefer not to say",
  consent: false,
  share: false,
  mode: "General",
  submitted: false,
  files: [],
  audio: false,
  lang: "en-IN",
  custom: "",
  summary: {},
};
const questions = [
  {
    title: "What brings you in today?",
    sub: "Choose what feels closest. You can tell us more in the next step.",
    options: [
      "Headache",
      "Fever or chills",
      "Stomach discomfort",
      "Something else",
    ],
  },
  {
    title: "When did it start?",
    sub: "An approximate time is helpful.",
    options: [
      "Today",
      "1–3 days ago",
      "About a week ago",
      "More than a week ago",
    ],
  },
  {
    title: "How much is it affecting your day?",
    sub: "Choose the description that best matches how you feel.",
    options: [
      "Mild · daily activities unaffected",
      "Moderate · some difficulty",
      "Severe · unable to do usual activities",
      "Not sure",
    ],
  },
  {
    title: "Is there anything else you feel?",
    sub: "Tell us about any other symptoms you have noticed.",
    options: [
      "No other symptoms",
      "Nausea or dizziness",
      "Chest pain with difficulty breathing",
      "Something else",
    ],
  },
  {
    title: "Any medicines or allergies to add?",
    sub: "Include regular medicines, supplements, and any known allergies.",
    options: [
      "No medicines or allergies",
      "I take regular medicines",
      "I have a known allergy",
      "I will discuss with the doctor",
    ],
  },
];
const ayush = [
  {
    title: "How has your appetite been?",
    sub: "Let us begin with your recent eating patterns.",
    options: [
      "Usual appetite",
      "Less than usual",
      "More than usual",
      "Varies through the day",
    ],
  },
  {
    title: "How have you been sleeping?",
    sub: "Think about the past week.",
    options: [
      "Restful sleep",
      "Difficulty falling asleep",
      "Waking frequently",
      "Sleeping more than usual",
    ],
  },
  {
    title: "How is your energy during the day?",
    sub: "Choose what matches your recent experience.",
    options: [
      "Usual energy",
      "Tired with light activity",
      "Tired after exercise",
      "Energy varies",
    ],
  },
  {
    title: "Have your daily habits changed?",
    sub: "Tell us about changes in food, exercise, or routine.",
    options: [
      "No changes",
      "Diet has changed",
      "Activity has changed",
      "Several changes",
    ],
  },
  {
    title: "Any medicines or allergies to add?",
    sub: "Include herbal preparations and supplements.",
    options: [
      "No medicines or allergies",
      "I take regular medicines",
      "I have a known allergy",
      "I will discuss with the doctor",
    ],
  },
];
const q = () => (state.mode === "AYUSH" ? ayush : questions)[state.q];
