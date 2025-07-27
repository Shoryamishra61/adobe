import Plot from 'react-plotly.js';
export default function ChartPanel({table,onHover}){
  const cols=Object.keys(table[0]); const x=table.map(r=>r[cols[0]]); const y=table.map(r=>+r[cols[1]]);
  return <Plot data={[{type:'bar',x,y,marker:{color:'teal'}}]}
           layout={{height:320}}
           onHover={d=>onHover(d.points[0].pointIndex)} />;
} 