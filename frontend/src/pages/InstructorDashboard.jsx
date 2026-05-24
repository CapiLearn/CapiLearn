import { Link } from "react-router-dom";
import "../styles/InstructorDashboard.css";

const summaryStats = [
  {
    label: "Active students",
    value: "18",
    helper: "Students active this week",
  },
  {
    label: "Questions asked",
    value: "142",
    helper: "Across all learning sessions",
  },
  {
    label: "Students to review",
    value: "4",
    helper: "May need instructor support",
  },
];

const topicDistribution = [
  {
    topic: "Ipsum Lorem...",
    count: 38,
    percentage: 78,
  },
  {
    topic: "Ipsum Lorem...",
    count: 31,
    percentage: 64,
  },
  {
    topic: "Ipsum Lorem...",
    count: 24,
    percentage: 50,
  },
  {
    topic: "Ipsum Lorem...",
    count: 19,
    percentage: 39,
  },
  {
    topic: "Ipsum Lorem...",
    count: 15,
    percentage: 31,
  },
];

const studentRoster = [
  {
    name: "John Carter",
    topTopic: "Ipsum Lorem",
    questions: 18,
    streak: "4 days",    
    lastActive: "Today",
  },
  {
    name: "Maya Singh",
    topTopic: "Ipsum Lorem",
    questions: 9,
    streak: "1 day",   
    lastActive: "Yesterday",
  },
  {
    name: "Luis Rivera",
    topTopic: "Ipsum Lorem",
    questions: 14,
    streak: "5 days",   
    lastActive: "Today",
  },
  {
    name: "Ava Thompson",
    topTopic: "Ipsum Lorem",
    questions: 6,
    streak: "6 days",    
    lastActive: "Today",
  },
  {
    name: "Noah Kim",
    topTopic: "Ipsum Lorem",
    questions: 7,
    streak: "3 days",    
    lastActive: "2 days ago",
  },
];

function InstructorDashboard() {
  return (
    <main className="instructor-page">
      <aside className="instructor-sidebar">
        <div className="instructor-brand">
          <div className="instructor-brand-icon">♧</div>
          <span>CapiLearn</span>
        </div>

        <nav className="instructor-nav">
          <button className="active">Dashboard</button>
          <button>Students</button>
          <button>Question Trends</button>          
        </nav>

        <Link className="instructor-logout-link" to="/">
          Log out
        </Link>

        <div className="instructor-profile-card">
          <div className="instructor-avatar">O</div>
          <div>
            <h3>Trogdor (He/Him/Burninator)</h3>
            <p>FCF Instructor</p>
          </div>
        </div>
      </aside>

      <section className="instructor-main">
        <header className="instructor-header">
          <div>
            <p className="instructor-kicker">Instructor Dashboard</p>
            <h1>Student learning insights</h1>
            <p>
              Monitor student activity, identify common areas of confusion, and
              see where instructor support may be needed.
            </p>
          </div>

          <button className="export-button">Export report</button>
        </header>

        <section className="instructor-stat-grid">
          {summaryStats.map((stat) => (
            <article className="instructor-stat-card" key={stat.label}>
              <p>{stat.label}</p>
              <h2>{stat.value}</h2>
              <span>{stat.helper}</span>
            </article>
          ))}
        </section>

        <section className="instructor-content-grid">
          <article className="instructor-panel topic-panel">
            <div className="panel-header">
              <div>
                <p className="panel-label">Question Trends</p>
                <h2>Common confusion topics</h2>
              </div>
              <span>This week</span>
            </div>

            <div className="topic-list">
              {topicDistribution.map((topic) => (
                <div className="topic-row" key={topic.topic}>
                  <div className="topic-info">
                    <h3>{topic.topic}</h3>
                    <p>{topic.count} questions</p>
                  </div>

                  <div className="topic-bar-block">
                    <div className="topic-bar">
                      <div
                        className="topic-fill"
                        style={{ width: `${topic.percentage}%` }}
                      ></div>
                    </div>
                    <span>{topic.percentage}%</span>
                  </div>
                </div>
              ))}
            </div>
          </article>
          
        </section>

        <section className="instructor-panel roster-panel">
          <div className="panel-header">
            <div>
              <p className="panel-label">Student Roster</p>
              <h2>Student activity overview</h2>
            </div>
            <button className="small-outline-button">View all students</button>
          </div>

          <div className="roster-table-wrapper">
            <table className="roster-table">
              <thead>
                <tr>
                  <th>Student</th>
                  <th>Top topic</th>
                  <th>Questions</th>
                  <th>Streak</th>                  
                  <th>Last active</th>
                </tr>
              </thead>

              <tbody>
                {studentRoster.map((student) => (
                  <tr key={student.name}>
                    <td>
                      <div className="student-cell">
                        <div className="student-initial">
                          {student.name.charAt(0)}
                        </div>
                        <span>{student.name}</span>
                      </div>
                    </td>
                    <td>{student.topTopic}</td>
                    <td>{student.questions}</td>
                    <td>{student.streak}</td>
                    <td>{student.lastActive}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </section>
    </main>
  );
}

export default InstructorDashboard;