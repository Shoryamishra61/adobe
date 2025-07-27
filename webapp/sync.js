export function chartSyncHighlight(idx){
  window.AdobeDC.View.getInstance().goToLocation({pageNumber:window.rowPage[idx]});
} 