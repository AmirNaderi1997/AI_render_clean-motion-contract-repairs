import React from "react";
import { useNavigate } from "react-router-dom";
import { Icon } from "./components/Icon";
import { templates } from "./templateData";

const categories = ["All", ...Array.from(new Set(templates.map(item => item.category)))];

export default function Templates() {
  const navigate = useNavigate();
  const [category, setCategory] = React.useState("All");
  const shown = templates.filter(item => category === "All" || item.category === category);
  return <div className="page">
    <header className="page-header">
      <div><h1>Templates</h1><p>Start from a workflow. Templates only pre-fill your request; you can change every decision in the conversation.</p></div>
    </header>
    <div className="chip-row" role="group" aria-label="Filter templates">
      {categories.map(item => <button key={item} className="chip" aria-pressed={category === item} onClick={() => setCategory(item)}>{item}</button>)}
    </div>
    <ul className="tpl-grid">
      {shown.map(item => <li key={item.id}>
        <button className="tpl-card" onClick={() => navigate(`/studio?template=${item.id}&prompt=${encodeURIComponent(item.prompt)}`)} aria-label={`Use template: ${item.title}`}>
          <span className="tpl-tile" aria-hidden="true"><Icon name={item.icon} size={26}/><span className="tpl-format">{item.format}</span></span>
          <span className="tpl-body">
            <span className="tpl-cat">{item.category}</span>
            <b>{item.title}</b>
            <span className="tpl-desc">{item.description}</span>
          </span>
          <span className="tpl-use">Use template<Icon name="chevron" size={16}/></span>
        </button>
      </li>)}
    </ul>
  </div>;
}
