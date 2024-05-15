// Parse and store title from the server's render since it may have been translated.
const defaultTitleElements = document.title.split('::');

if (defaultTitleElements.length !== 3) {
  console.error('Could not parse site title while adding proposal title change listener.');
} else {
  document.getElementById('id_title').addEventListener('change', (event) => {
    const newTitle = event.target.value;
    if (newTitle === '') {
      document.title = defaultTitleElements.join(' :: ');
    } else {
      document.title = `${newTitle} :: ${defaultTitleElements[1]} :: ${defaultTitleElements[2]}`;
    }
  });
}
