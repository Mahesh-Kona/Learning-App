import { useEffect, useMemo, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import * as XLSX from "xlsx";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";

export default function CourseCompletionAnalytics({ studentId }) {
  const [data, setData] = useState([]);
  const [view, setView] = useState("day");
  const [year, setYear] = useState("2025");
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState("date");
  const [sortOrder, setSortOrder] = useState("asc");
  const [page, setPage] = useState(1);

  const PAGE_SIZE = 7;

  useEffect(() => {
    fetch(`/api/v1/students/${studentId}/courses-completed?view=${view}&year=${year}`)
      .then((res) => res.json())
      .then((payload) => {
        // Support both bare array and wrapped { data: [...] }
        if (Array.isArray(payload)) {
          setData(payload);
        } else if (payload && Array.isArray(payload.data)) {
          setData(payload.data);
        } else {
          setData([]);
        }
      });
  }, [studentId, view, year]);

  /* ---------- Derived Metrics ---------- */

  const streak = useMemo(() => {
    if (view !== "day") return null;
    let count = 0;
    const sorted = [...data].sort((a, b) => new Date(b.date) - new Date(a.date));
    for (let row of sorted) {
      if (row.completed > 0) count++;
      else break;
    }
    return count;
  }, [data, view]);

  const bestRecord = useMemo(() => {
    if (data.length === 0) return null;
    return data.reduce((best, cur) => (cur.completed > best.completed ? cur : best));
  }, [data]);

  const processedData = useMemo(() => {
    let filtered = data.filter((d) =>
      d.date.toLowerCase().includes(search.toLowerCase())
    );

    filtered.sort((a, b) => {
      const valA = a[sortKey];
      const valB = b[sortKey];
      if (typeof valA === "number") {
        return sortOrder === "asc" ? valA - valB : valB - valA;
      }
      return sortOrder === "asc"
        ? valA.localeCompare(valB)
        : valB.localeCompare(valA);
    });

    return filtered;
  }, [data, search, sortKey, sortOrder]);

  const paginatedData = processedData.slice(
    (page - 1) * PAGE_SIZE,
    page * PAGE_SIZE
  );

  const totalCompleted = processedData.reduce((s, r) => s + r.completed, 0);

  const toggleSort = (key) => {
    if (sortKey === key) setSortOrder(sortOrder === "asc" ? "desc" : "asc");
    else {
      setSortKey(key);
      setSortOrder("asc");
    }
  };

  const exportExcel = () => {
    const ws = XLSX.utils.json_to_sheet(processedData);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, "Completions");
    XLSX.writeFile(wb, `course_completion_${year}_${view}.xlsx`);
  };

  return (
    <div className="p-6 bg-slate-50 min-h-screen space-y-6">
      {/* Stats Row */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {view === "day" && (
          <Card className="rounded-2xl shadow-sm">
            <CardContent className="p-4">
              <p className="text-sm text-slate-500">Current Streak</p>
              <p className="text-2xl font-semibold">🔥 {streak} days</p>
            </CardContent>
          </Card>
        )}

        {bestRecord && (
          <Card className="rounded-2xl shadow-sm">
            <CardContent className="p-4">
              <p className="text-sm text-slate-500">Best {view === "day" ? "Day" : "Month"}</p>
              <p className="text-xl font-semibold">🏆 {bestRecord.date}</p>
              <p className="text-slate-600">{bestRecord.completed} courses</p>
            </CardContent>
          </Card>
        )}

        <Card className="rounded-2xl shadow-sm">
          <CardContent className="p-4">
            <p className="text-sm text-slate-500">Total Completed</p>
            <p className="text-2xl font-semibold">{totalCompleted}</p>
          </CardContent>
        </Card>
      </div>

      {/* Mini Trend Graph */}
      <Card className="rounded-2xl shadow-sm">
        <CardContent className="p-4">
          <p className="font-medium mb-2">Completion Trend</p>
          <div className="h-[180px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={processedData}>
                <XAxis dataKey="date" hide />
                <YAxis hide />
                <Tooltip />
                <Line type="monotone" dataKey="completed" strokeWidth={3} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>

      {/* Table */}
      <Card className="rounded-2xl shadow-sm">
        <CardContent className="p-6 space-y-4">
          <div className="flex flex-wrap justify-between items-center gap-4">
            <h2 className="text-lg font-medium">Courses Completed</h2>

            <div className="flex gap-2 flex-wrap">
              <select value={view} onChange={(e) => setView(e.target.value)} className="border rounded-lg px-3 py-2 text-sm">
                <option value="day">Per Day</option>
                <option value="month">Per Month</option>
              </select>

              <select value={year} onChange={(e) => setYear(e.target.value)} className="border rounded-lg px-3 py-2 text-sm">
                <option value="2025">2025</option>
                <option value="2024">2024</option>
              </select>

              <input
                placeholder={`Search ${view === "day" ? "date" : "month"}`}
                className="border rounded-lg px-3 py-2 text-sm"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />

              <button onClick={exportExcel} className="bg-green-600 text-white px-4 py-2 rounded-lg text-sm">
                Export Excel
              </button>
            </div>
          </div>

          <table className="min-w-full border border-slate-200 rounded-lg">
            <thead className="bg-slate-100">
              <tr>
                <th onClick={() => toggleSort("date")} className="cursor-pointer px-4 py-2 text-left">
                  {view === "day" ? "Date" : "Month"}
                </th>
                <th onClick={() => toggleSort("completed")} className="cursor-pointer px-4 py-2 text-left">
                  Courses Completed
                </th>
              </tr>
            </thead>
            <tbody>
              {paginatedData.map((row, i) => (
                <tr key={i} className="border-t">
                  <td className="px-4 py-2">{row.date}</td>
                  <td className="px-4 py-2 font-medium">{row.completed}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}
