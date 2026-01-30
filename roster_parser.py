def _extract_header_info(self, header):
        # Assuming header is a dictionary containing relevant information
        header_info = {}

        # Lines 224-232 fixed with 8 spaces indentation
        header_info['title'] = header.get('title', '')
        header_info['author'] = header.get('author', '')
        header_info['date'] = header.get('date', '')
        header_info['summary'] = header.get('summary', '')

        # Additional lines can be added below with the same indentation

        header_info['keywords'] = header.get('keywords', '')
        header_info['version'] = header.get('version', '')
        header_info['footer'] = header.get('footer', '')

        return header_info
